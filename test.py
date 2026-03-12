import asyncio
import sys

# Windows compatibility (ignored on Linux)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.control.voice_assistance.utils import fresh_state
from src.control.voice_assistance.graph import build_response_graph

response_graph = build_response_graph()


async def chat_loop():
    # initialize state using your schema
    state = fresh_state()

    state = fresh_state()

    state["call_to_number"] = "debug"
    state["call_sid"] = "debug123"
    state["identity_user_name"] = "prabha"
    state["identity_user_phone"] = "9524650818"
    state["identity_user_email"] = "prabhamuruganantham06@gmail.com"

    while True:
        user_input = input("User: ")

        if user_input.lower() in ["exit", "quit"]:
            break

        # schema requires speech_user_text
        state["speech_user_text"] = user_input

        result = await response_graph.ainvoke(state)

        ai_text = result.get("speech_ai_text")
        print("AI:", ai_text)

        # update state for next turn
        state = result


if __name__ == "__main__":
    asyncio.run(chat_loop())





# from passlib.context import CryptContext

# pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# def get_password_hash(password: str):
#     return pwd_context.hash(password)

# password = "Saravanan@012"

# hashed_password = get_password_hash(password)

# print(hashed_password)