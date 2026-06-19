"""
Core agent — orchestrates all subsystems into a single conversation loop.
Uses Groq (Meta Llama) as the LLM engine via core.llm.
"""
import json
import config
import core.identity as identity
import core.llm as llm
from core.inner_state import InnerState
from core.kernel import CognitiveKernel
from core.priority_memory import PriorityMemory
from core.memory import (
    EpisodicMemory, SemanticMemory, SelfModel,
    PersonalityMemory, UserProfile, ThoughtsMemory, ConsolidationMemory
)
from core.reflection import (
    run_session_summary, run_red_thread_update, run_daily_reflection,
    run_weekly_essence,
)
from tools.file_tools import read_note, write_note, list_notes, TOOL_DEFINITIONS
from tools.construction_tools import CONSTRUCTION_TOOL_DEFINITIONS, dispatch_construction_tool
from tools.community_tools import COMMUNITY_TOOL_DEFINITIONS, dispatch_community_tool
import pipeline.projects as proj
import pipeline.community as community_db

ALL_TOOLS = TOOL_DEFINITIONS + CONSTRUCTION_TOOL_DEFINITIONS + COMMUNITY_TOOL_DEFINITIONS
_CONSTRUCTION_TOOL_NAMES = {t["function"]["name"] for t in CONSTRUCTION_TOOL_DEFINITIONS}
_COMMUNITY_TOOL_NAMES    = {t["function"]["name"] for t in COMMUNITY_TOOL_DEFINITIONS}


class Agent:
    def __init__(self):
        identity.ensure_identity_files()

        self.episodic     = EpisodicMemory()
        self.semantic     = SemanticMemory()
        self.self_model   = SelfModel()
        self.personality  = PersonalityMemory()
        self.user_profile = UserProfile()
        self.thoughts     = ThoughtsMemory()
        self.lmcs         = ConsolidationMemory()

        self.inner_state = InnerState()
        self.pms         = PriorityMemory()
        self.kernel      = CognitiveKernel(self.inner_state, self.lmcs)

        self.session_id = self.episodic.new_session()
        proj.init_db()
        community_db.init_db()

        self._run_background_cycles()

    def _run_background_cycles(self):
        if self.kernel.should_run_daily_reflection():
            try:
                run_daily_reflection(self.episodic, self.semantic, self.lmcs, self.pms)
            except Exception:
                pass
        if self.kernel.should_run_weekly_essence():
            try:
                run_weekly_essence(self.lmcs, self.pms)
            except Exception:
                pass

    def _build_system_prompt(self) -> str:
        return identity.build_system_prompt(
            priority_memory_str=self.pms.to_context_string(),
            inner_state_str=self.inner_state.to_context_string(),
            personality_str=self.personality.state_summary(),
        )

    def _build_messages(self, conversation_history: list[dict]) -> list[dict]:
        recent = self.episodic.recent_turns(config.EPISODIC_CONTEXT_TURNS)
        injected = [{"role": t["role"], "content": t["content"]} for t in recent]
        live_contents = {m["content"] for m in conversation_history
                         if isinstance(m.get("content"), str)}
        merged = [m for m in injected if m["content"] not in live_contents]
        merged.extend(conversation_history)
        return merged

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "read_note":
            return read_note(tool_input["filename"])
        elif tool_name == "write_note":
            return write_note(tool_input["filename"], tool_input["content"])
        elif tool_name == "list_notes":
            return json.dumps(list_notes())
        elif tool_name == "write_journal":
            identity.append_journal(tool_input["entry"])
            return "[Journal updated]"
        elif tool_name == "update_knowledge":
            identity.append_knowledge(tool_input["content"])
            self.semantic.store(tool_input["content"], category="knowledge", importance=1.5)
            return "[Knowledge base updated]"
        elif tool_name == "remember_this":
            content    = tool_input["content"]
            category   = tool_input.get("category", "Learning")
            importance = float(tool_input.get("importance", 1.0))
            self.semantic.store(content, category=category.lower(), importance=importance)
            self.pms.add_insight(content, category=category, importance=importance)
            return "[Stored in semantic memory]"
        elif tool_name == "update_projects":
            identity.update_projects(tool_input["content"])
            return "[Projects updated]"
        elif tool_name == "add_self_rule":
            rule    = tool_input["rule"]
            context = tool_input.get("context", "")
            rules   = identity.load_self_rules()
            if rule not in rules:
                rules.append(rule)
                identity.save_self_rules(rules)
                self.self_model.add_rule(rule, context)
            return f"[Self-rule added: {rule}]"
        elif tool_name == "update_inner_state":
            if "current_focus"       in tool_input: self.inner_state.set_focus(tool_input["current_focus"])
            if "priority_direction"  in tool_input: self.inner_state.set_priority_direction(tool_input["priority_direction"])
            if "close_loop"          in tool_input: self.inner_state.close_loop(tool_input["close_loop"])
            if "complete_task"       in tool_input: self.inner_state.complete_task(tool_input["complete_task"])
            if "add_continuity_note" in tool_input: self.inner_state.add_continuity_note(tool_input["add_continuity_note"])
            self.inner_state.save()
            return "[Inner state updated]"
        elif tool_name in _CONSTRUCTION_TOOL_NAMES:
            return dispatch_construction_tool(tool_name, tool_input)
        elif tool_name in _COMMUNITY_TOOL_NAMES:
            return dispatch_community_tool(tool_name, tool_input)
        return f"[Unknown tool: {tool_name}]"

    def chat(self, user_message: str,
             conversation_history: list[dict]) -> tuple[str, list[dict]]:
        """Process one user turn. Returns (response_text, updated_history)."""
        self.kernel.on_user_message(user_message)

        relevant = self.semantic.search(user_message, limit=5)
        user_content = user_message
        if relevant:
            mem_block = "\n".join(f"• {m['content']}" for m in relevant)
            user_content = f"{user_message}\n\n[Relevant memories]\n{mem_block}"

        history = list(conversation_history)
        history.append({"role": "user", "content": user_content})
        self.episodic.add_turn(self.session_id, "user", user_message)

        system_prompt = self._build_system_prompt()
        full_messages  = [{"role": "system", "content": system_prompt}] + \
                         self._build_messages(history)

        final_response = ""
        for _ in range(6):  # max tool rounds
            text, tool_calls = llm.chat_with_tools(full_messages, ALL_TOOLS)

            if text:
                final_response = text

            if not tool_calls:
                break

            full_messages.append(llm.assistant_tool_message(text, tool_calls))
            for tc in tool_calls:
                result = self._dispatch_tool(tc["name"], tc["arguments"])
                full_messages.append(llm.tool_result_message(tc["id"], result))

        self.kernel.on_agent_response(final_response)
        self.episodic.add_turn(self.session_id, "assistant", final_response)
        self.inner_state.save()

        history.append({"role": "assistant", "content": final_response})

        if self.kernel.should_update_red_thread():
            try:
                run_red_thread_update(
                    self.inner_state,
                    self.episodic.recent_turns(config.RED_THREAD_INTERVAL)
                )
            except Exception:
                pass

        return final_response, history

    def end_session(self):
        turns = self.episodic.recent_turns(50)
        try:
            run_session_summary(
                self.session_id, turns, self.episodic,
                self.semantic, self.pms, self.user_profile
            )
        except Exception:
            pass
        self.inner_state.reset_session_turn()
        self.inner_state.save()
        self.pms.save()
