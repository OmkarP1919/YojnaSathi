import json
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import Scheme, SchemeListResponse, SingleSchemeResponse

# Load environment variables
load_dotenv()

app = FastAPI(
    title="YojnaSathi API",
    description="Backend API for YojnaSathi - simplifying government scheme access for citizens.",
    version="0.2.0",
)

# Enable CORS for frontend development
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.json"


def load_schemes_data() -> List[Scheme]:
    """Load and parse schemes data from schemes.json."""
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw_schemes = json.load(f)
    return [Scheme(**item) for item in raw_schemes]


@app.get("/api/health")
def health_check():
    """Service health check endpoint."""
    return {
        "status": "ok",
        "service": "YojnaSathi",
    }


@app.get("/api/schemes", response_model=SchemeListResponse)
def get_schemes(
    category: Optional[str] = Query(None, description="Filter by scheme category (e.g., agriculture, health)"),
    state: Optional[str] = Query(None, description="Filter by state (e.g., all-india, maharashtra)"),
    target_group: Optional[str] = Query(None, description="Filter by target group (e.g., women, farmers)"),
):
    """Retrieve all schemes with optional case-insensitive filtering."""
    schemes = load_schemes_data()

    if category:
        cat_filter = category.strip().lower()
        schemes = [s for s in schemes if s.category.lower() == cat_filter]

    if state:
        state_filter = state.strip().lower()
        schemes = [s for s in schemes if s.state.lower() == state_filter]

    if target_group:
        tg_filter = target_group.strip().lower()
        schemes = [
            s
            for s in schemes
            if any(tg_filter == tg.lower() or tg_filter in tg.lower() for tg in s.target_groups)
        ]

    return SchemeListResponse(
        success=True,
        count=len(schemes),
        schemes=schemes,
    )


@app.get("/api/schemes/{scheme_id}", response_model=SingleSchemeResponse)
def get_scheme_by_id(scheme_id: str):
    """Retrieve a single scheme by its unique identifier."""
    schemes = load_schemes_data()
    target_id = scheme_id.strip().lower()

    for s in schemes:
        if s.id.lower() == target_id:
            return SingleSchemeResponse(
                success=True,
                scheme=s,
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scheme with id '{scheme_id}' not found",
    )
