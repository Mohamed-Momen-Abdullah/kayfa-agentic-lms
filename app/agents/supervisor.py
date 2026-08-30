import os
import sys
import asyncio
from datetime import datetime
from typing import Optional, List, Literal
from contextlib import AsyncExitStack

from pydantic import BaseModel, Field
from groq import Groq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.core.program import LLMTextCompletionProgram
from llama_index.llms.groq import Groq as LlamaGroq

# Import from modular components
from app.agents.config import (
    GROQ_MODEL, GROQ_API_KEY, ROLE_PERMISSIONS, AGENT_DESCRIPTIONS, 
    AGENT_TOOLS, AGENT_CONTEXTS, DATABASE_CONTEXT,
    AGENT_TEMPERATURE, ROUTER_TEMPERATURE, FINAL_TEMPERATURE,
    WEB_SEARCH_MODEL, WEB_SEARCH_TEMPERATURE, WEB_SEARCH_MAX_RESULTS
)
from app.services.sentiment import sentiment_engine, clean_markdown_formatting
from app.retrieval.rag import init_hybrid_agent_system, is_iq_query
from app.retrieval.cache import check_semantic_cache, update_cache
from app.data.connector import get_personal_records
from app.observability.tracing import lf

class RouteDecision(BaseModel):
    destinations: List[Literal[
        "Instructor_Agent", "Course_Agent", "Graduation_Agent", "Attendance_Agent",
        "Schedule_Agent", "Policy_Agent", "Analytics_Agent", "Recommendation_Agent", "Assessment_Agent",
    ]] = Field(default=["Course_Agent"])
    reason: str = Field(description="A brief explanation for the selected agents.")

class MCPClient:
    GREETING_PATTERNS = {"كيفك", "ازيك", "السلام عليكم", "سلام", "مرحبا", "أهلاً", "اهلا", "hi", "hello", "hey", "صباح الخير", "مساء الخير", "من أنت", "مين أنت"}

    def __init__(self):
        self.sessions = []
        self.tool_to_session_map = {}
        self.exit_stack = AsyncExitStack()
        self.tool_call_log = []
        self.last_routing_info = {"destinations": [], "reason": ""}

        self.llama_llm = LlamaGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=AGENT_TEMPERATURE, reasoning_effort="none")
        self.router_llm = LlamaGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=ROUTER_TEMPERATURE, reasoning_effort="none")
        self.raw_groq = Groq(api_key=GROQ_API_KEY)

        self.rag_resources = init_hybrid_agent_system()
        self.hybrid_retriever = self.rag_resources["hybrid_retriever"]
        
        self.router_program = LLMTextCompletionProgram.from_defaults(
            output_cls=RouteDecision,
            prompt_template_str="""
IDENTITY & ROLE: You are the Supervisor Router...
Current user request: "{query}"
Available agents: {allowed_agents_desc}
Return destinations and reason""",
            llm=self.router_llm,
            verbose=False,
        )

    async def connect_to_server(self, server_script_path: str):
        if not os.path.exists(server_script_path): return
        env = os.environ.copy()
        command = sys.executable if server_script_path.endswith(".py") else "node"
        server_params = StdioServerParameters(command=command, args=[server_script_path], env=env)
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()
        self.sessions.append(session)
        response = await session.list_tools()
        for tool in response.tools: self.tool_to_session_map[tool.name] = session

    async def _get_all_tools(self):
        all_tools = []
        for session in self.sessions:
            try: all_tools.extend((await session.list_tools()).tools)
            except Exception: pass
        return all_tools

    def _convert_mcp_to_llamaindex_tool(self, mcp_tool, session) -> FunctionTool:
        async def mock_fn(**kwargs):
            try:
                response = await session.call_tool(mcp_tool.name, arguments=kwargs)
                return response.content[0].text if response.content else ""
            except Exception as e: return str(e)
        return FunctionTool.from_defaults(fn=mock_fn, name=mcp_tool.name, description=mcp_tool.description)

    def _search_internal_knowledge(self, query: str) -> str:
        if not self.hybrid_retriever: return "STATUS: SEARCH_ERROR\nRetriever unavailable."
        try:
            search_query = f"{query} IQ quiz test" if is_iq_query(query) else query
            results = self.hybrid_retriever.retrieve(search_query)
            if is_iq_query(query):
                iq_terms = ("iq", "intelligence", "quiz", "test", "سؤال", "اختبار", "ذكاء")
                results = [item for item in results if any(t in str(item.get_content()).lower() for t in iq_terms)]
            if not results: return "STATUS: NOT_FOUND"
            
            lines = ["STATUS: FOUND", "INTERNAL SOURCE(S):"]
            for i, item in enumerate(results[:5], 1):
                lines.append(f"[{i}]\n{str(item.get_content()).strip()}")
            return "\n\n".join(lines)
        except Exception as e: return f"STATUS: SEARCH_ERROR\n{e}"

    def _web_search(self, query: str) -> str:
        try:
            completion = self.raw_groq.chat.completions.create(
                model=WEB_SEARCH_MODEL,
                messages=[{"role": "user", "content": f"Search the web for: {query}"}],
                tools=[{"type": "browser_search"}],
                tool_choice="required",
                temperature=WEB_SEARCH_TEMPERATURE,
            )
            return f"STATUS: FOUND\nWEB RESULTS:\n{(completion.choices[0].message.content or '').strip()}"
        except Exception as e: return f"STATUS: SEARCH_ERROR\n{e}"

    def _build_search_tools(self) -> list:
        return [
            FunctionTool.from_defaults(fn=self._search_internal_knowledge, name="search_internal_knowledge"),
            FunctionTool.from_defaults(fn=self._web_search, name="web_search")
        ]

    def _create_agent(self, agent_name, raw_mcp_tools, user_role, user_id=None, preflight_search_context="") -> Optional[ReActAgent]:
        allowed = ROLE_PERMISSIONS.get(user_role, {}).get("allowed_agents", [])
        if agent_name not in allowed: return None
        
        allowed_tool_names = set(AGENT_TOOLS.get(agent_name, []))
        llama_tools = [self._convert_mcp_to_llamaindex_tool(t, self.tool_to_session_map[t.name]) for t in raw_mcp_tools if t.name in allowed_tool_names and t.name in self.tool_to_session_map]
        llama_tools.extend(self._build_search_tools())
        
        system_prompt = DATABASE_CONTEXT + "\n\n" + AGENT_CONTEXTS.get(agent_name, "") + f"\nUSER ID: {user_id}\nROLE: {user_role}\nPREFLIGHT: {preflight_search_context}"
        return ReActAgent(tools=llama_tools, llm=self.llama_llm, verbose=False, system_prompt=system_prompt)

    async def orchestrate_query(self, query: str, user_role: str) -> List[str]:
        allowed = ROLE_PERMISSIONS.get(user_role, {}).get("allowed_agents", ["Course_Agent"])
        try:
            decision = await self.router_program.acall(query=query, allowed_agents_desc=", ".join(allowed))
            filtered = [d for d in decision.destinations if d in allowed]
            self.last_routing_info = {"destinations": filtered or [allowed[0]], "reason": decision.reason}
            return filtered or [allowed[0]]
        except Exception: return [allowed[0]]

    async def process_query_for_api(self, query, user_id, user_role=None, history=None):
        clean_query = query.strip().strip("؟?").lower()
        if clean_query in self.GREETING_PATTERNS or len(clean_query) < 4:
            return {"response": ROLE_PERMISSIONS.get(user_role, {}).get("welcome_msg", "أهلاً بك!"), "sentiment": None}

        cached_answer, status = check_semantic_cache(query)
        if cached_answer: return {"response": cached_answer, "sentiment": None}

        user_sentiment = sentiment_engine.predict(query)
        target_agents = await self.orchestrate_query(query, user_role)

        preflight = self._search_internal_knowledge(query) if is_iq_query(query) else ""
        if preflight.startswith("STATUS: NOT_FOUND"): preflight += "\n\n" + self._web_search(query)

        rag_nodes = self.hybrid_retriever.retrieve(query) if self.hybrid_retriever else []
        rag_context = "\n".join([n.get_content() for n in rag_nodes[:2]]) if rag_nodes else "No info"
        personal_context = get_personal_records(user_role, str(user_id))
        
        mcp_tools = await self._get_all_tools()
        tasks = []
        for name in target_agents:
            agent = self._create_agent(name, mcp_tools, user_role, str(user_id), preflight)
            if agent: tasks.append(agent.aquery(query))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        agents_feedback = "\n\n---\n\n".join([str(r) for r in results if not isinstance(r, Exception)])

        messages = [{"role": "system", "content": f"Answer concisely based on the data. Personal Context: {personal_context}. Agent Feedback: {agents_feedback}. RAG: {rag_context}"}]
        if history: messages.extend(history)
        messages.append({"role": "user", "content": query})

        generation = None
        if lf:
            try:
                trace = lf.trace(name="process_query", user_id=str(user_id), metadata={"routing": self.last_routing_info}, input={"query": query})
                generation = trace.generation(name="groq_gen", model=GROQ_MODEL, input=messages)
            except Exception: pass

        response = self.raw_groq.chat.completions.create(model=GROQ_MODEL, messages=messages, temperature=FINAL_TEMPERATURE)
        final_text = clean_markdown_formatting(response.choices[0].message.content)
        
        if generation:
            try: generation.end(output=final_text)
            except Exception: pass
            
        update_cache(query, final_text)
        return {"response": final_text, "sentiment": sentiment_engine.predict(final_text)}

    async def cleanup(self):
        if hasattr(self, "exit_stack") and self.exit_stack:
            await self.exit_stack.aclose()
