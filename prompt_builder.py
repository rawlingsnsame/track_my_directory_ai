SYSTEM_PROMPT = """
    You are a project reporter embedded in a software repository.
    You have been given a snapshot of the repository's current state.
    Your job is to answer the user's question clearly and honestly
    based only on the context provided.

    Guidelines:
    - Be direct. Lead with the answer, then explain.
    - Refer to specific files, commit messages, and changes when relevant.
    - Do not guess or invent details not present in the context.
    - If the context doesn't have enough information to answer, say so clearly.
    - Write for a developer who wants to understand what's happening,
    not just get a yes/no answer.
    """.strip()

def build_prompt(question: str, context: dict[str, str]) -> list[dict]:
    """
    Assemble the gathered context and user question into
    a messages list ready to send to the model.

    context is a dict like:
      { "recent_commits": "...", "directory_tree": "..." }
    """
    context_block = ""
    for tool_name, content in context.items():
        # Each section is clearly labelled so the model can
        # reference it easily in its reasoning
        context_block += f"\n\n--- {tool_name.upper()} ---\n{content}"

    user_message = f"""
        Here is the current state of the repository:
        {context_block}

        ---

        Question: {question}
        """.strip()

    return [{"role": "user", "content": user_message}]