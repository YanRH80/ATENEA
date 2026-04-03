"""
atenea/advisor.py — AI Advisor: Meta-Learning Loop

Transversal module that acts as a co-pilot for the learning system.
The AI can:
1. Detect the academic domain of content
2. Propose prompt specialization for the domain
3. Interpret natural language feedback from the user
4. Suggest priority adjustments based on performance patterns
5. Evolve prompts based on performance data
6. Log all advisory actions for audit

Principle: "La IA propone, el humano dispone."
Every suggestion requires explicit user approval.

Pipeline position:
    Transversal — reads from all pipeline outputs, proposes changes to config.
"""

import json
import logging

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from atenea import ai, storage
from atenea.utils import generate_id
from config import defaults, prompts as prompts_config
from config import advisor as advisor_config

console = Console()
log = logging.getLogger(__name__)


# ============================================================
# DOMAIN DETECTION
# ============================================================

def analyze_domain(clean_md, model=None):
    """Detect the academic domain of the content.

    Uses the LLM to classify the content's domain, subdomain,
    and academic level from keywords and section titles.

    Args:
        clean_md: Dict from clean-md.json.
        model: Override model.

    Returns:
        dict — {domain, subdomain, level, confidence, key_terminology}
    """
    keywords = clean_md.get("keywords", [])[:50]
    section_titles = [s["title"] for s in clean_md.get("sections", [])]

    prompt = prompts_config.DETECT_DOMAIN_PROMPT.format(
        keywords=json.dumps(keywords, ensure_ascii=False),
        section_titles=json.dumps(section_titles, ensure_ascii=False),
        language_instruction=ai.get_language_instruction("es"),
    )

    try:
        result = ai.call_llm_json(prompt, model=model, task="domain_detection")
        if isinstance(result, dict):
            return result
    except Exception as e:
        log.warning(f"Domain detection failed: {e}")

    return {
        "domain": "general",
        "subdomain": "unknown",
        "level": "unknown",
        "confidence": 0.0,
        "key_terminology": [],
    }


# ============================================================
# PROMPT SPECIALIZATION
# ============================================================

def suggest_prompt_specialization(domain, model=None):
    """Suggest how to specialize prompts for a detected domain.

    Args:
        domain: Dict from analyze_domain().
        model: Override model.

    Returns:
        list[dict] — suggestions, each with:
            prompt_name, current_snippet, suggested_snippet, reason
    """
    domain_name = domain.get("domain", "general")
    subdomain = domain.get("subdomain", "")
    terminology = domain.get("key_terminology", [])

    if domain_name == "general":
        return []

    suggestions = []

    # Suggest specializing the extraction prompts role
    role_current = "Eres un experto en análisis ontológico"
    role_suggested = (
        f"Eres un experto en {domain_name}"
        f"{f' ({subdomain})' if subdomain else ''} "
        f"especializado en análisis ontológico"
    )

    suggestions.append({
        "prompt_name": "EXTRACT_PATHS_PROMPT",
        "section": "Rol",
        "current_snippet": role_current,
        "suggested_snippet": role_suggested,
        "reason": f"Domain detected: {domain_name}/{subdomain} "
                  f"(confidence: {domain.get('confidence', 0):.0%}). "
                  f"Specializing the role improves extraction accuracy.",
    })

    # Suggest adding domain terminology to extraction
    if terminology:
        terms_str = ", ".join(terminology[:10])
        suggestions.append({
            "prompt_name": "EXTRACT_POINTS_PROMPT",
            "section": "Criterios de selección",
            "current_snippet": "Preferir términos técnicos sobre términos genéricos",
            "suggested_snippet": (
                f"Preferir términos técnicos sobre términos genéricos. "
                f"Terminología clave del dominio: {terms_str}"
            ),
            "reason": "Adding domain-specific terminology helps the LLM "
                      "prioritize relevant technical terms.",
        })

    return suggestions


# ============================================================
# USER FEEDBACK PROCESSING
# ============================================================

def process_user_feedback(feedback, project_name, model=None):
    """Interpret natural language feedback and propose actions.

    Args:
        feedback: Free text from the user (e.g., "me cuestan las justificaciones").
        project_name: Project name (to load analytics context).
        model: Override model.

    Returns:
        dict — {interpretation, proposed_actions, follow_up_question}
    """
    # Load analytics for context
    analytics = storage.load_json(
        storage.get_project_path(project_name, "analisis.json")
    ) or {}

    # Build context summary
    overall = analytics.get("overall", {})
    per_comp = analytics.get("per_component", {})
    trends = analytics.get("session_trends", [])

    analytics_summary = json.dumps({
        "overall_mastery": overall.get("level", "new"),
        "overall_wilson": overall.get("wilson_score", 0),
        "total_reviews": overall.get("total", 0),
    }, ensure_ascii=False)

    cspoj_performance = json.dumps(per_comp, ensure_ascii=False)

    session_history = json.dumps(
        trends[-5:] if trends else [],
        ensure_ascii=False,
    )

    prompt = prompts_config.PROCESS_FEEDBACK_PROMPT.format(
        analytics_summary=analytics_summary,
        cspoj_performance=cspoj_performance,
        session_history=session_history,
        user_feedback=feedback,
        language_instruction=ai.get_language_instruction("es"),
    )

    try:
        result = ai.call_llm_json(prompt, model=model, task="advisor")
        if isinstance(result, dict):
            return result
    except Exception as e:
        log.warning(f"Feedback processing failed: {e}")

    return {
        "interpretation": "No pude interpretar el feedback.",
        "proposed_actions": [],
        "follow_up_question": None,
    }


# ============================================================
# PRIORITY ADJUSTMENT SUGGESTIONS
# ============================================================

def suggest_priority_adjustment(project_name):
    """Suggest priority weight adjustments based on performance patterns.

    Analyzes analytics to detect patterns and proposes changes to
    config/defaults.py priority weights.

    Args:
        project_name: Project name.

    Returns:
        list[dict] — suggestions with variable, current, proposed, reason.
    """
    analytics = storage.load_json(
        storage.get_project_path(project_name, "analisis.json")
    ) or {}

    per_comp = analytics.get("per_component", {})
    weak = analytics.get("weak_areas", [])
    suggestions = []

    # If justification is consistently weak, suggest increasing its weight
    just_stats = per_comp.get("justification", {})
    if just_stats.get("total", 0) >= 5 and just_stats.get("wilson_score", 1) < 0.3:
        suggestions.append({
            "variable": "W_URGENCY",
            "current": defaults.W_URGENCY,
            "proposed": min(defaults.W_URGENCY + 0.05, 0.50),
            "reason": "Justification mastery is very low — increase urgency weight "
                      "to prioritize weak items more aggressively.",
        })

    # If accuracy is consistently high, suggest reducing session size
    trends = analytics.get("session_trends", [])
    if len(trends) >= 3:
        recent_acc = [t.get("accuracy", 0) for t in trends[-3:]]
        avg_acc = sum(recent_acc) / len(recent_acc)
        if avg_acc > 0.9:
            suggestions.append({
                "variable": "DEFAULT_QUESTIONS_PER_TEST",
                "current": defaults.DEFAULT_QUESTIONS_PER_TEST,
                "proposed": max(defaults.DEFAULT_QUESTIONS_PER_TEST - 5, defaults.MIN_SESSION_SIZE),
                "reason": f"Average accuracy is {avg_acc:.0%} over last 3 sessions. "
                          f"Consider shorter sessions with harder questions.",
            })

    return suggestions


# ============================================================
# PROMPT EVOLUTION
# ============================================================

def evolve_prompt(prompt_name, project_name, model=None):
    """Propose an improved version of a prompt based on performance data.

    Args:
        prompt_name: Name of the prompt (e.g., "EXTRACT_PATHS_PROMPT").
        project_name: Project name.
        model: Override model.

    Returns:
        dict — {analysis, evolved_prompt, changes_summary, expected_improvement}
    """
    # Get current prompt
    current_prompt = getattr(prompts_config, prompt_name, None)
    if not current_prompt:
        return {"error": f"Prompt '{prompt_name}' not found"}

    # Load performance data
    data = storage.load_json(
        storage.get_project_path(project_name, "data.json")
    ) or {}
    analytics = storage.load_json(
        storage.get_project_path(project_name, "analisis.json")
    ) or {}

    # Build performance metrics
    stats = data.get("extraction_stats", {})
    performance_metrics = json.dumps(stats, ensure_ascii=False)

    # Detect common errors
    common_errors = []
    just_rate = stats.get("justification_verbatim_rate", {}).get("value", 1)
    if just_rate < 0.9:
        common_errors.append(
            f"Justification verbatim rate is {just_rate:.0%} (target: 95%). "
            f"LLM is paraphrasing instead of quoting."
        )
    coverage = stats.get("section_coverage", {}).get("value", 1)
    if coverage < 0.9:
        common_errors.append(
            f"Section coverage is {coverage:.0%}. Some sections are not generating paths."
        )

    # Domain info
    clean_md_path = None
    sources = storage.list_sources(project_name)
    if sources:
        clean_md_path = storage.get_source_path(project_name, sources[-1], "clean-md.json")
    clean_md = storage.load_json(clean_md_path) if clean_md_path else {}
    domain_info = "general"
    if clean_md:
        domain = analyze_domain(clean_md, model=model)
        domain_info = f"{domain.get('domain', 'general')}/{domain.get('subdomain', '')}"

    prompt = prompts_config.EVOLVE_PROMPT_PROMPT.format(
        prompt_name=prompt_name,
        current_prompt=current_prompt[:2000],
        performance_metrics=performance_metrics,
        common_errors=json.dumps(common_errors, ensure_ascii=False),
        domain_info=domain_info,
        language_instruction=ai.get_language_instruction("es"),
    )

    try:
        result = ai.call_llm_json(prompt, model=model, task="prompt_evolution")
        if isinstance(result, dict):
            return result
    except Exception as e:
        log.warning(f"Prompt evolution failed: {e}")

    return {"error": "Prompt evolution failed"}


# ============================================================
# ACTION LOGGING
# ============================================================

def log_advisor_action(action, project_name):
    """Log an advisory action for audit.

    Args:
        action: Dict with action details.
        project_name: Project name.
    """
    log_path = storage.get_project_path(project_name, "advisor-log.json")
    log_data = storage.load_json(log_path)
    if not isinstance(log_data, list):
        log_data = []

    action["timestamp"] = storage.now_iso()
    action["id"] = generate_id("adv")
    log_data.append(action)

    storage.save_json(log_data, log_path)


# ============================================================
# INTERACTIVE SESSION
# ============================================================

def run_advisor_session(project_name, feedback=None, suggest_only=False,
                        evolve_prompts=False, model=None):
    """Run an interactive AI advisor session.

    Modes:
    - Default: Full interactive session with suggestions and feedback
    - --feedback: Quick feedback processing
    - --suggest: Show suggestions only, no interaction
    - --evolve-prompts: Propose prompt improvements

    Args:
        project_name: Project name.
        feedback: Quick feedback text (skip interactive mode).
        suggest_only: Only show suggestions, no interaction.
        evolve_prompts: Propose prompt improvements.
        model: Override model.
    """
    console.print(Panel(
        f"[bold]AI Advisor[/bold] — Project: {project_name}\n"
        f"[dim]La IA propone, el humano dispone.[/dim]",
        title="Atenea Advisor",
    ))

    # Quick feedback mode
    if feedback:
        console.print(f"\n[bold]Processing feedback:[/bold] {feedback}")
        result = process_user_feedback(feedback, project_name, model=model)
        _display_feedback_result(result, project_name)
        return

    # Domain detection
    console.print("\n[bold]1. Domain Analysis[/bold]")
    sources = storage.list_sources(project_name)
    if sources:
        clean_md_path = storage.get_source_path(
            project_name, sources[-1], "clean-md.json"
        )
        clean_md = storage.load_json(clean_md_path) or {}
        if clean_md:
            domain = analyze_domain(clean_md, model=model)
            console.print(f"  Domain: [bold]{domain.get('domain', '?')}[/bold] "
                          f"/ {domain.get('subdomain', '?')}")
            console.print(f"  Level: {domain.get('level', '?')} "
                          f"(confidence: {domain.get('confidence', 0):.0%})")

            # Prompt specialization suggestions
            suggestions = suggest_prompt_specialization(domain, model=model)
            if suggestions:
                console.print(f"\n[bold]2. Prompt Specialization Suggestions[/bold]")
                for i, s in enumerate(suggestions, 1):
                    console.print(f"\n  [bold]{i}.[/bold] {s['prompt_name']} → {s['section']}")
                    console.print(f"  [red]Current:[/red] {s['current_snippet'][:80]}")
                    console.print(f"  [green]Suggested:[/green] {s['suggested_snippet'][:80]}")
                    console.print(f"  [dim]Reason: {s['reason']}[/dim]")

                    if not suggest_only:
                        if Confirm.ask("  Apply this suggestion?", default=False):
                            log_advisor_action({
                                "type": "prompt_specialization",
                                "suggestion": s,
                                "decision": "accepted",
                            }, project_name)
                            console.print("  [green]✓ Logged (edit config/prompts.py to apply)[/green]")
                        else:
                            log_advisor_action({
                                "type": "prompt_specialization",
                                "suggestion": s,
                                "decision": "rejected",
                            }, project_name)

    # Priority adjustment suggestions
    console.print(f"\n[bold]3. Priority Adjustment Suggestions[/bold]")
    priority_suggestions = suggest_priority_adjustment(project_name)
    if priority_suggestions:
        for s in priority_suggestions:
            console.print(f"  {s['variable']}: {s['current']} → {s['proposed']}")
            console.print(f"  [dim]{s['reason']}[/dim]")
    else:
        console.print("  [dim]No adjustments suggested (need more session data)[/dim]")

    # Prompt evolution
    if evolve_prompts:
        console.print(f"\n[bold]4. Prompt Evolution[/bold]")
        for prompt_name in ["EXTRACT_POINTS_PROMPT", "EXTRACT_PATHS_PROMPT"]:
            console.print(f"\n  Analyzing {prompt_name}...")
            result = evolve_prompt(prompt_name, project_name, model=model)
            if "error" in result:
                console.print(f"  [yellow]{result['error']}[/yellow]")
            else:
                console.print(f"  [bold]Analysis:[/bold] {result.get('analysis', '')[:150]}")
                changes = result.get("changes_summary", [])
                for c in changes[:3]:
                    console.print(f"    - {c}")

                if not suggest_only:
                    if Confirm.ask("  Save evolved prompt version?", default=False):
                        _save_prompt_version(prompt_name, result, project_name)
                        console.print("  [green]✓ Version saved[/green]")

    # Interactive feedback loop
    if not suggest_only and not feedback:
        console.print(f"\n[bold]Feedback[/bold]")
        console.print("[dim]Escribe tu feedback en lenguaje natural, o 'q' para salir.[/dim]")

        while True:
            user_input = Prompt.ask("[bold cyan]Feedback[/bold cyan]")
            if user_input.strip().lower() in ("q", "quit", "exit", ""):
                break

            result = process_user_feedback(user_input, project_name, model=model)
            _display_feedback_result(result, project_name)

    console.print("\n[dim]Session complete.[/dim]")


def _display_feedback_result(result, project_name):
    """Display the result of processing user feedback."""
    interpretation = result.get("interpretation", "")
    if interpretation:
        console.print(f"\n  [bold]Interpretation:[/bold] {interpretation}")

    actions = result.get("proposed_actions", [])
    if actions:
        console.print(f"\n  [bold]Proposed Actions:[/bold]")
        for i, action in enumerate(actions, 1):
            console.print(f"  {i}. {action.get('description', '?')}")
            changes = action.get("config_changes", [])
            for c in changes:
                console.print(f"     {c.get('variable', '?')}: "
                              f"{c.get('current', '?')} → {c.get('proposed', '?')}")

            if Confirm.ask(f"  Apply action {i}?", default=False):
                log_advisor_action({
                    "type": "feedback_action",
                    "action": action,
                    "decision": "accepted",
                }, project_name)
                console.print("  [green]✓ Logged[/green]")

    follow_up = result.get("follow_up_question")
    if follow_up:
        console.print(f"\n  [bold]Follow-up:[/bold] {follow_up}")


def _save_prompt_version(prompt_name, evolution_result, project_name):
    """Save an evolved prompt version to prompt-versions.json."""
    versions_path = storage.get_project_path(project_name, "prompt-versions.json")
    versions = storage.load_json(versions_path)
    if not isinstance(versions, dict):
        versions = {"versions": []}

    existing = [v for v in versions["versions"] if v["prompt_name"] == prompt_name]
    version_num = max((v.get("version", 0) for v in existing), default=0) + 1

    versions["versions"].append({
        "prompt_name": prompt_name,
        "version": version_num,
        "content": evolution_result.get("evolved_prompt", ""),
        "created_at": storage.now_iso(),
        "created_by": "advisor",
        "changes": evolution_result.get("changes_summary", []),
        "analysis": evolution_result.get("analysis", ""),
        "performance": None,
    })

    storage.save_json(versions, versions_path)
