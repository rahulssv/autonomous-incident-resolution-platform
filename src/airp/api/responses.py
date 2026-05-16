PAGINATED_LIST_RESPONSES = {
    200: {
        "description": "Paginated list response.",
        "content": {
            "application/json": {
                "example": {
                    "items": [],
                    "total": 0,
                    "limit": 100,
                    "offset": 0,
                }
            }
        },
    }
}
