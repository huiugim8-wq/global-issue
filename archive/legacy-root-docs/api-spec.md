# Global Issue Map

## API 명세서

---

## 1. API 개요

본 API는 세계 주요 이슈 뉴스 서비스를 위한 백엔드 인터페이스이다.
전쟁, 경제, 자연재해, 정치 카테고리별 뉴스 조회, 홈 화면 지도 데이터 조회, 대륙별/키워드별 검색, AI 분석 조회, 기사 저장 및 삭제 기능을 제공한다.

---

## 2. 기본 정보

**Base URL**

```text
/api
```

**Response Format**

```json
{
  "success": true,
  "message": "요청 성공",
  "data": {}
}
```

**Error Format**

```json
{
  "success": false,
  "message": "에러 메시지",
  "error_code": "ERROR_CODE"
}
```

---

# 3. 공통 데이터 모델

## 3.1 News Object

```json
{
  "id": "news_001",
  "title": "중동 지역 군사 긴장 고조",
  "source": "Reuters",
  "published_at": "2026-03-11T09:30:00Z",
  "summary": "중동 지역에서 군사적 긴장이 다시 높아지고 있다.",
  "country": "Israel",
  "continent": "Asia",
  "region": "Middle East",
  "category": "war",
  "keywords": ["middle east", "military", "conflict"],
  "lat": 31.0461,
  "lng": 34.8516,
  "importance": 5,
  "pin_size": "large",
  "pin_color": "#EF4444"
}
```

---

## 3.2 AI Analysis Object

```json
{
  "article_id": "news_001",
  "interpretation": "이번 뉴스는 지역 안보 긴장 심화를 의미한다.",
  "prediction": "향후 주변국 개입 가능성과 국제 유가 변동성이 커질 수 있다.",
  "impact": {
    "gold": "상승 가능성",
    "oil": "상승 가능성",
    "stocks": "변동성 확대",
    "exchange_rate": "안전자산 선호 증가"
  }
}
```

---

## 3.3 Saved Article Object

```json
{
  "id": "saved_001",
  "article_id": "news_001",
  "title": "중동 지역 군사 긴장 고조",
  "category": "war",
  "continent": "Asia",
  "region": "Middle East",
  "source": "Reuters",
  "summary": "중동 지역에서 군사적 긴장이 다시 높아지고 있다.",
  "saved_at": "2026-03-11T12:00:00Z"
}
```

---

# 4. API 목록

## 4.1 홈 지도 뉴스 조회

### GET `/api/news/home`

홈 화면에서 사용할 전체 뉴스 핀 데이터와 주요 뉴스 카드 데이터를 조회한다.
지도에는 카테고리별 색상 핀이 표시되며, 카드에는 영향력 높은 뉴스 5개를 제공한다. 

### Query Parameters

| 이름        | 타입     | 필수 | 설명             |
| --------- | ------ | -: | -------------- |
| continent | string |  N | 특정 대륙 필터       |
| keyword   | string |  N | 키워드 검색         |
| limit     | int    |  N | 카드 뉴스 개수, 기본 5 |

### Example Request

```http
GET /api/news/home?continent=Asia&keyword=oil&limit=5
```

### Example Response

```json
{
  "success": true,
  "message": "홈 뉴스 조회 성공",
  "data": {
    "map_pins": [
      {
        "id": "news_001",
        "title": "중동 지역 군사 긴장 고조",
        "continent": "Asia",
        "category": "war",
        "lat": 31.0461,
        "lng": 34.8516,
        "importance": 5,
        "pin_size": "large",
        "pin_color": "#EF4444"
      }
    ],
    "top_headlines": [
      {
        "id": "news_001",
        "title": "중동 지역 군사 긴장 고조",
        "category": "war",
        "continent": "Asia",
        "source": "Reuters",
        "summary": "중동 지역에서 군사적 긴장이 다시 높아지고 있다."
      }
    ]
  }
}
```

---

## 4.2 카테고리별 뉴스 조회

### GET `/api/news/category/{category}`

전쟁, 경제, 자연재해, 정치 중 특정 카테고리의 뉴스를 조회한다.
카테고리 페이지에서는 중요도에 따라 핀 크기와 강조가 달라진다. 

### Path Parameters

| 이름       | 타입     | 설명                                            |
| -------- | ------ | --------------------------------------------- |
| category | string | `war`, `economy`, `disaster`, `politics` 중 하나 |

### Query Parameters

| 이름        | 타입     | 필수 | 설명                     |
| --------- | ------ | -: | ---------------------- |
| continent | string |  N | 대륙 필터                  |
| keyword   | string |  N | 키워드 필터                 |
| sort      | string |  N | `latest`, `importance` |
| limit     | int    |  N | 최대 개수                  |

### Example Request

```http
GET /api/news/category/war?continent=Asia&keyword=missile&sort=importance&limit=20
```

### Example Response

```json
{
  "success": true,
  "message": "카테고리 뉴스 조회 성공",
  "data": {
    "category": "war",
    "articles": [
      {
        "id": "news_001",
        "title": "중동 지역 군사 긴장 고조",
        "source": "Reuters",
        "published_at": "2026-03-11T09:30:00Z",
        "summary": "중동 지역에서 군사적 긴장이 다시 높아지고 있다.",
        "country": "Israel",
        "continent": "Asia",
        "lat": 31.0461,
        "lng": 34.8516,
        "importance": 5,
        "pin_size": "large",
        "pin_color": "#B91C1C"
      }
    ]
  }
}
```

---

## 4.3 대륙별 뉴스 조회

### GET `/api/news/continent/{continent}`

특정 대륙 기준으로 뉴스 목록과 핀 데이터를 조회한다.
홈이나 검색 결과에서 대륙별 탐색 기능을 위해 사용한다.

### Path Parameters

| 이름        | 타입     | 설명                                                                    |
| --------- | ------ | --------------------------------------------------------------------- |
| continent | string | `Asia`, `Europe`, `Africa`, `NorthAmerica`, `SouthAmerica`, `Oceania` |

### Query Parameters

| 이름       | 타입     | 필수 | 설명      |
| -------- | ------ | -: | ------- |
| category | string |  N | 카테고리 필터 |
| keyword  | string |  N | 키워드 필터  |
| limit    | int    |  N | 조회 개수   |

### Example Request

```http
GET /api/news/continent/Asia?category=economy&keyword=trade
```

### Example Response

```json
{
  "success": true,
  "message": "대륙별 뉴스 조회 성공",
  "data": {
    "continent": "Asia",
    "articles": [
      {
        "id": "news_101",
        "title": "아시아 무역 긴장 확산",
        "category": "economy",
        "source": "BBC",
        "lat": 35.6762,
        "lng": 139.6503,
        "importance": 4,
        "pin_color": "#16A34A"
      }
    ]
  }
}
```

---

## 4.4 통합 뉴스 검색

### GET `/api/news/search`

홈 화면의 검색창에서 사용하는 API이다.
사용자가 원하는 기사 키워드를 입력하면, 제목/요약/키워드/지역 기준으로 뉴스를 검색한다. 검색 결과는 리스트와 지도 핀으로 함께 사용된다.

### Query Parameters

| 이름        | 타입     | 필수 | 설명      |
| --------- | ------ | -: | ------- |
| q         | string |  Y | 검색 키워드  |
| continent | string |  N | 대륙 필터   |
| category  | string |  N | 카테고리 필터 |
| limit     | int    |  N | 최대 개수   |
| page      | int    |  N | 페이지 번호  |

### Example Request

```http
GET /api/news/search?q=gold&continent=Asia&category=war&limit=10&page=1
```

### Example Response

```json
{
  "success": true,
  "message": "검색 성공",
  "data": {
    "query": "gold",
    "total": 12,
    "page": 1,
    "articles": [
      {
        "id": "news_001",
        "title": "중동 긴장에 금 가격 상승",
        "category": "war",
        "continent": "Asia",
        "source": "Reuters",
        "summary": "안전자산 선호로 금값이 상승하고 있다.",
        "lat": 31.0461,
        "lng": 34.8516,
        "importance": 5,
        "pin_size": "large",
        "pin_color": "#EF4444"
      }
    ]
  }
}
```

---

## 4.5 기사 상세 조회

### GET `/api/news/{article_id}`

특정 기사 1개의 상세 정보와 지도 표시용 정보를 조회한다.

### Path Parameters

| 이름         | 타입     | 설명    |
| ---------- | ------ | ----- |
| article_id | string | 기사 ID |

### Example Request

```http
GET /api/news/news_001
```

### Example Response

```json
{
  "success": true,
  "message": "기사 상세 조회 성공",
  "data": {
    "id": "news_001",
    "title": "중동 지역 군사 긴장 고조",
    "source": "Reuters",
    "published_at": "2026-03-11T09:30:00Z",
    "summary": "중동 지역에서 군사적 긴장이 다시 높아지고 있다.",
    "content": "기사 본문 요약 또는 정제된 텍스트",
    "country": "Israel",
    "continent": "Asia",
    "region": "Middle East",
    "category": "war",
    "keywords": ["military", "oil", "conflict"],
    "lat": 31.0461,
    "lng": 34.8516,
    "importance": 5
  }
}
```

---

## 4.6 AI 분석 조회

### GET `/api/news/{article_id}/analysis`

선택한 기사에 대한 AI 해석, 예상 동향, 영향 분석 결과를 조회한다.
카테고리 페이지에서 핀 클릭 후 상세 패널에 노출된다.

### Example Request

```http
GET /api/news/news_001/analysis
```

### Example Response

```json
{
  "success": true,
  "message": "AI 분석 조회 성공",
  "data": {
    "article_id": "news_001",
    "interpretation": "이번 사건은 지역 안보 불안을 높이고 있다.",
    "prediction": "주변국 개입 가능성과 원자재 가격 변동성이 커질 수 있다.",
    "impact": {
      "gold": "상승 가능성",
      "oil": "상승 가능성",
      "stocks": "하락 압력",
      "exchange_rate": "변동성 확대"
    }
  }
}
```

---

## 4.7 기사 저장

### POST `/api/articles/save`

사용자가 관심 있는 기사를 저장한다.
카테고리 페이지의 저장 버튼과 연결된다.

### Request Body

```json
{
  "article_id": "news_001"
}
```

### Example Response

```json
{
  "success": true,
  "message": "기사 저장 성공",
  "data": {
    "saved_id": "saved_001",
    "article_id": "news_001"
  }
}
```

---

## 4.8 저장 기사 목록 조회

### GET `/api/articles/saved`

나만의 기사 페이지에서 저장된 기사 목록을 조회한다.
카테고리별 정렬/필터를 지원한다. 

### Query Parameters

| 이름        | 타입     | 필수 | 설명                   |
| --------- | ------ | -: | -------------------- |
| category  | string |  N | 카테고리 필터              |
| continent | string |  N | 대륙 필터                |
| sort      | string |  N | `latest`, `category` |

### Example Request

```http
GET /api/articles/saved?category=war&sort=latest
```

### Example Response

```json
{
  "success": true,
  "message": "저장 기사 조회 성공",
  "data": {
    "articles": [
      {
        "id": "saved_001",
        "article_id": "news_001",
        "title": "중동 지역 군사 긴장 고조",
        "category": "war",
        "continent": "Asia",
        "source": "Reuters",
        "summary": "중동 지역에서 군사적 긴장이 다시 높아지고 있다.",
        "saved_at": "2026-03-11T12:00:00Z"
      }
    ]
  }
}
```

---

## 4.9 저장 기사 삭제

### DELETE `/api/articles/saved/{saved_id}`

나만의 기사 페이지에서 저장한 기사를 삭제한다.

### Path Parameters

| 이름       | 타입     | 설명       |
| -------- | ------ | -------- |
| saved_id | string | 저장 기사 ID |

### Example Request

```http
DELETE /api/articles/saved/saved_001
```

### Example Response

```json
{
  "success": true,
  "message": "저장 기사 삭제 성공",
  "data": {
    "deleted_id": "saved_001"
  }
}
```

---

# 5. 핀 표시 규칙

카테고리별 핀 색상은 다음 기준을 사용한다. 

| 카테고리     | 색상 |
| -------- | -- |
| war      | 빨강 |
| economy  | 초록 |
| politics | 노랑 |
| disaster | 주황 |

중요도별 핀 크기 규칙은 다음과 같다. 

| importance | pin_size |
| ---------- | -------- |
| 5          | large    |
| 3~4        | medium   |
| 1~2        | small    |

---

# 6. 추천 MongoDB 인덱스

기사 사이트에서 **정확하게 대륙별 / 키워드별 뉴스**를 빠르게 찾으려면 아래 인덱스를 권장한다.

## news 컬렉션

* `category`
* `continent`
* `country`
* `published_at`
* `importance`
* `keywords`
* `title` + `summary` 텍스트 인덱스

예시

```python
await db.news.create_index([("category", 1)])
await db.news.create_index([("continent", 1)])
await db.news.create_index([("keywords", 1)])
await db.news.create_index([("published_at", -1)])
await db.news.create_index([("importance", -1)])
await db.news.create_index([("title", "text"), ("summary", "text")])
```

## saved_articles 컬렉션

* `article_id`
* `saved_at`
* `category`

---

# 7. 구현 우선순위

실제로 먼저 만들 API 순서는 이게 제일 좋다.

1. `GET /api/news/home`
2. `GET /api/news/category/{category}`
3. `GET /api/news/search`
4. `GET /api/news/{article_id}`
5. `GET /api/news/{article_id}/analysis`
6. `POST /api/articles/save`
7. `GET /api/articles/saved`
8. `DELETE /api/articles/saved/{saved_id}`

이 순서면
**홈 → 카테고리 → 검색 → 상세 → 저장** 흐름이 자연스럽게 완성된다.

---

# 8. 한 줄 정리

이 API 구조는
**홈에서 전체 이슈 탐색 → 대륙/키워드/카테고리별 검색 → 기사 상세/AI 분석 확인 → 저장 기사 관리** 흐름을 기준으로 설계되었다.

       
