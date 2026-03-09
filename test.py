# import asyncio
# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# from src.control.voice_assistance.utils import fresh_state
# from src.control.voice_assistance.graph import build_response_graph

# response_graph = build_response_graph()

# async def chat_loop():
#     state = fresh_state(to_number="debug", call_sid="debug123")

#     while True:
#         user_input = input("User: ")

#         if user_input.lower() in ["exit", "quit"]:
#             break

#         state["user_text"] = user_input
#         result = await response_graph.ainvoke(state)

#         print("AI:", result.get("ai_text"))
#         state = result

# asyncio.run(chat_loop())





from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def get_password_hash(password: str):
    return pwd_context.hash(password)

password = "Saravanan@012"

hashed_password = get_password_hash(password)

print(hashed_password)