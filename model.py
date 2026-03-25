from utils.config import get_answer
from prompt_builder import build_prompt

def answer(question: str, context: dict[str, str]) -> str:
    """
    Given a user question and the gathered context, build a prompt
    and ask the model to answer it.
    """
    messages = build_prompt(question, context)
    #print(f"Prompt messages: {messages}")  # Debug print to see the final prompt
    response = get_answer(messages)
    print(f"AI response: {response}")
    return response
