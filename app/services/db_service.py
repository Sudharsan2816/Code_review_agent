"""MongoDB persistence layer for review history."""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.models.review import CodeReview


class DatabaseService:
    """Async MongoDB client for storing and querying code reviews."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongodb_uri)
        self._db: AsyncIOMotorDatabase = self._client[settings.mongodb_db_name]

    @property
    def reviews(self):
        return self._db["reviews"]

    async def save_review(self, review: CodeReview) -> str:
        """
        Persist a :class:`CodeReview` document and return its ``_id`` string.
        """
        doc = review.model_dump(mode="json")
        doc["created_at"] = datetime.utcnow()
        result = await self.reviews.insert_one(doc)
        review_id = str(result.inserted_id)
        logger.info(f"Review saved with id={review_id}")
        return review_id

    async def get_review(self, review_id: str) -> Optional[dict]:
        """Retrieve a review document by its MongoDB ObjectId string."""
        try:
            doc = await self.reviews.find_one({"_id": ObjectId(review_id)})
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as exc:
            logger.error(f"get_review error: {exc}")
            return None

    async def update_review_approval(
        self, review_id: str, approved_by: str, posted: bool
    ) -> bool:
        """Mark a review as approved and (optionally) posted."""
        result = await self.reviews.update_one(
            {"_id": ObjectId(review_id)},
            {
                "$set": {
                    "approved_by": approved_by,
                    "posted_to_github": posted,
                    "approved_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count == 1

    async def list_reviews(
        self,
        repo: Optional[str] = None,
        limit: int = 20,
        skip: int = 0,
    ) -> list[dict]:
        """Return a paginated list of reviews, optionally filtered by repo."""
        query: dict = {}
        if repo:
            query["repo"] = repo

        cursor = self.reviews.find(query).sort("created_at", -1).skip(skip).limit(limit)
        docs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            docs.append(doc)
        return docs

    async def close(self) -> None:
        """Close the MongoDB connection."""
        self._client.close()
