"""
Core agent — orchestrates all subsystems into a single conversation loop.
"""
import json
from datetime import datetime
import anthropic
import config
import core.identity as identity
from core.inner_state import InnerState
from core.kernel import CognitiveKernel
from core.priority_memory import PriorityMemory
from core.memory import (
    EpisodicMemory, SemanticMemory, SelfModel,
    PersonalityMemory, UserProfile, ThoughtsMemory, ConsolidationMemory
)
from core.reflection import (
    run_session_summary, run_red_thread_update, run_daily_reflection,
    run_weekly_essence, run_anchor_review
)
from tools.file_tools import (
    read_note, write_note, list_notes, TOOL_DEFINITIONS
)
import tools.file_tools as file_tools


class Agent:
    def __init__(self):
        identity.ensure_identity_files()

        self.episodic   = EpisodicMemory()
        self.semantic   = SemanticMemory()
        self.self_model = SelfModel()
        self.personality = PersonalityMemory()
        self.user_profile = UserProfile()
        self.thoughts   = ThoughtsMemory()
        self.lmcs       = ConsolidationMemory()

        self.inner_state = InnerState()
        self.pms         = PriorityMemory()
        self.kernel      = CognitiveKernel(self.inner_state, self.lmcs)

        self.session_id  = self.episodic.new_session()
        self.client      = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        self._run_background_cycles()

    def _run_background_cycles(self):
        """Run any due reflection/consolidation cycles at startup."""
        if self.kernel.should_run_daily_reflection():
            try:
                run_daily_reflection(
                    self.episodic, self.semantic, self.lmcs, self.pms
                )
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
        """Inject recent episodic turns before the live conversation."""
        recent = self.episodic.recent_turns(config.EPISODIC_CONTEXT_TURNS)

        # Convert stored turns to message format
        injected = []
        for t in recent:
            injected.append({"role": t["role"], "content": t["content"]})

        # Merge with live history (avoid duplicates)
        live_contents = {m["content"] for m in conversation_history}
        merged = [m for m in injected if m["content"] not in live_contents]
        merged.extend(conversation_history)

        return merged

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "read_note":
            return read_note(tool_input["filename"])

        elif tool_name == "write_note":
            return write_note(tool_input["filename"], tool_input["content"])

        elif tool_name == "list_notes":
            notes = list_notes()
            return json.dumps(notes)

        elif tool_name == "write_journal":
            identity.append_journal(tool_input["entry"])
            return "[Journal updated]"

        elif tool_name == "update_knowledge":
            identity.append_knowledge(tool_input["content"])
            self.semantic.store(tool_input["content"], category="knowledge", importance=1.5)
            return "[Knowledge base updated]"

        elif tool_name == "remember_this":
            content = tool_input["content"]
            category = tool_input.get("category", "Learning")
            importance = float(tool_input.get("importance", 1.0))
            self.semantic.store(content, category=category.lower(), importance=importance)
            self.pms.add_insight(content, category=category, importance=importance)
            return "[Stored in semantic memory]"

        elif tool_name == "update_projects":
            identity.update_projects(tool_input["content"])
            return "[Projects updated]"

        elif tool_name == "add_self_rule":
            rule = tool_input["rule"]
            context = tool_input.get("context", "")
            rules = identity.load_self_rules()
            if rule not in rules:
                rules.append(rule)
                identity.save_self_rules(rules)
                self.self_model.add_rule(rule, context)
            return f"[Self-rule added: {rule}]"

        elif tool_name == "update_inner_state":
            if "current_focus" in tool_input:
                self.inner_state.set_focus(tool_input["current_focus"])
            if "priority_direction" in tool_input:
                self.inner_state.set_priority_direction(tool_input["priority_direction"])
            if "close_loop" in tool_input:
                self.inner_state.close_loop(tool_input["close_loop"])
            if "complete_task" in tool_input:
                self.inner_state.complete_task(tool_input["complete_task"])
            if "add_continuity_note" in tool_input:
                self.inner_state.add_continuity_note(tool_input["add_continuity_note"])
            self.inner_state.save()
            return "[Inner state updated]"

        return f"[Unknown tool: {tool_name}]"

    def chat(self, user_message: str, conversation_history: list[dict]) -> tuple[str, list[dict]]:
        """
        Process one user turn.
        Returns (assistant_response, updated_conversation_history).
        """
        self.kernel.on_user_message(user_message)

        # Search semantic memory for relevant context
        relevant = self.semantic.search(user_message, limit=5)
        context_injection = ""
        if relevant:
            context_injection = "\n\n[Relevant memories]\n" + "\n".join(
                f"• {m['content']}" for m in relevant
            )

        # Add user turn
        history = list(conversation_history)
        user_content = user_message
        if context_injection:
            user_content = user_message + context_injection
        history.append({"role": "user", "content": user_content})

        # Store in episodic memory
        self.episodic.add_turn(self.session_id, "user", user_message)

        system_prompt = self._build_system_prompt()
        messages = self._build_messages(history)

        # Agentic loop (handles tool use)
        final_response = ""
        while True:
            response = self.client.messages.create(
                model=config.MODEL,
                max_tokens=2048,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Collect text blocks
            text_blocks = [b.text for b in response.content if b.type == "text"]
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if text_blocks:
                final_response = "\n".join(text_blocks)

            if response.stop_reason == "end_turn" or not tool_uses:
                break

            # Execute tools and feed results back
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                result = self._dispatch_tool(tu.name, tu.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result
                })
            messages.append({"role": "user", "content": tool_results})

        # Post-response updates
        self.kernel.on_agent_response(final_response)
        self.episodic.add_turn(self.session_id, "assistant", final_response)
        self.inner_state.save()

        # Add clean assistant turn to history
        history.append({"role": "assistant", "content": final_response})

        # Red thread update every N turns
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
        """Summarize and close the current session."""
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
