from pydantic import BaseModel



class HomeGameItem(BaseModel):
    game_id: int
    title: str
    thumbnail_url: str | None
    genres: list[str]
    rating: float | None
    is_new: bool = False

def _rating_from_score(review_score: float | None) -> float | None:
    """review_score(0~100%) → 5점 척도."""
    if review_score is None:
        return None
    return round(float(review_score) / 20, 1)