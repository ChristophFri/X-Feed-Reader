"""User and settings CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from web.db.encryption import encrypt
from web.models.user import User
from web.models.user_settings import UserSettings
from web.schemas.settings import SettingsUpdate


async def get_user_with_settings(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.settings)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_settings(db: AsyncSession, user_id: int) -> UserSettings:
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def update_settings(
    db: AsyncSession, user_id: int, updates: SettingsUpdate
) -> UserSettings:
    settings = await get_or_create_settings(db, user_id)

    update_data = updates.model_dump(exclude_unset=True)
    # Encrypt sensitive fields
    if "telegram_bot_token" in update_data and update_data["telegram_bot_token"]:
        update_data["telegram_bot_token"] = encrypt(update_data["telegram_bot_token"])

    for key, value in update_data.items():
        setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)
    return settings
