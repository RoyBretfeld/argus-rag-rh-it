from fastapi import APIRouter
from pydantic import BaseModel
from api.chat_handler import ChatHandler

router = APIRouter()

try:
    from core.rag.rag_pipeline import RAGPipeline
    from core.search.web_search_pipeline import WebSearchPipeline
    from core.llm.model_router import ModelRouter
    handler = ChatHandler(
        rag_pipeline=RAGPipeline(),
        web_search_pipeline=WebSearchPipeline(),
        model_router=ModelRouter()
    )
except ImportError as e:
    print(f"Warning: RAG imports failed in chat.py: {e}")
    handler = ChatHandler()

from typing import Optional

class ChatRequest(BaseModel):
    frage: str
    modus: str = "wissensbasis"  # wissensbasis, internet, beides
    vertraulich: bool = False
    filter_metadata: Optional[dict] = None

@router.post("")
async def chat_message(request: ChatRequest):
    try:
        result = handler.answer(
            frage=request.frage,
            modus=request.modus,
            vertraulich=request.vertraulich,
            filter_metadata=request.filter_metadata
        )
        return {"response": result}
    except Exception as e:
        return {"error": str(e)}
