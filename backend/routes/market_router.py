from __future__ import annotations

from fastapi import APIRouter

from backend.services.market_service import market_service

router = APIRouter(prefix='/api/market', tags=['market'])


@router.get('/gold')
async def get_gold() -> dict:
    return await market_service.get_gold()


@router.get('/wti')
async def get_wti() -> dict:
    return await market_service.get_wti()


@router.get('/sp500')
async def get_sp500() -> dict:
    return await market_service.get_sp500()
