     1|from __future__ import annotations
     2|
     3|import asyncio
     4|import csv
     5|import io
     6|import json
     7|from datetime import datetime, timezone
     8|from typing import Any
     9|
    10|import aiohttp
    11|
    12|from app.config import Settings
    13|
    14|
    15|class PocketBaseError(RuntimeError):
    16|    pass
    17|
    18|
    19|USER_COLLECTION = "tg_users"
    20|
    21|
    22|class PocketBaseClient:
    23|    def __init__(self, settings: Settings) -> None:
    24|        self.settings = settings
    25|        self._token: str | None = None
    26|        self._session: aiohttp.ClientSession | None = None
    27|
    28|    async def __aenter__(self) -> "PocketBaseClient":
    29|        self._session = aiohttp.ClientSession()
    30|        await self.wait_until_ready()
    31|        await self.auth_admin()
    32|        return self
    33|
    34|    async def __aexit__(self, *_: object) -> None:
    35|        if self._session:
    36|            await self._session.close()
    37|
    38|    @property
    39|    def session(self) -> aiohttp.ClientSession:
    40|        if not self._session:
    41|            raise PocketBaseError("PocketBase client is not started")
    42|        return self._session
    43|
    44|    async def wait_until_ready(self, timeout: int = 60) -> None:
    45|        last_error: Exception | None = None
    46|        for _ in range(timeout):
    47|            try:
    48|                async with self.session.get(f"{self.settings.pocketbase_url}/api/health") as response:
    49|                    if response.status < 500:
    50|                        return
    51|            except Exception as exc:  # pragma: no cover - network timing
    52|                last_error = exc
    53|            await asyncio.sleep(1)
    54|        raise PocketBaseError(f"PocketBase is not reachable: {last_error}")
    55|
    56|    async def auth_admin(self) -> None:
    57|        payload = {
    58|            "identity": self.settings.pocketbase_admin_email,
    59|            "password": self.settings.pocketbase_admin_password,
    60|        }
    61|        data = await self._request(
    62|            "POST",
    63|            "/api/admins/auth-with-password",
    64|            json=payload,
    65|            auth=False,
    66|        )
    67|        self._token = data["token"]
    68|
    69|    async def _request(
    70|        self,
    71|        method: str,
    72|        path: str,
    73|        *,
    74|        auth: bool = True,
    75|        **kwargs: Any,
    76|    ) -> Any:
    77|        headers = kwargs.pop("headers", {})
    78|        if auth and self._token:
    79|            headers["Authorization"] = f"Bearer {self._token}"
    80|        async with self.session.request(
    81|            method,
    82|            f"{self.settings.pocketbase_url}{path}",
    83|            headers=headers,
    84|            **kwargs,
    85|        ) as response:
    86|            if response.status >= 400:
    87|                body = await response.text()
    88|                raise PocketBaseError(f"{method} {path} failed with {response.status}: {body}")
    89|            if response.status == 204:
    90|                return None
    91|            return await response.json()
    92|
    93|async def ensure_schema(self) -> None:
    94|        collections = await self._request("GET", "/api/collections?perPage=200")
    95|        existing = {item["name"]: item for item in collections.get("items", [])}
    96|        for collection_cfg in collection_definitions():
    97|            name = collection_cfg["name"]
    98|            if name not in existing:
    99|                await self._request("POST", "/api/collections", json=collection_cfg)
   100|                continue
   101|            existing_collection = existing[name]
   102|            existing_fields = {field["name"]: field for field in existing_collection.get("schema", [])}
   103|            new_schema = list(existing_collection.get("schema", []))
   104|            changed = False
   105|            for field_cfg in collection_cfg["schema"]:
   106|                fname = field_cfg["name"]
   107|                if fname not in existing_fields:
   108|                    new_schema.append(field_cfg)
   109|                    changed = True
   110|                elif field_cfg.get("type") == "select":
   111|                    # Update select options (for e.g. adding "cancelled" to status)
   112|                    existing_field = existing_fields[fname]
   113|                    existing_opts = set(existing_field.get("options", {}).get("values", []))
   114|                    new_opts = set(field_cfg.get("options", {}).get("values", []))
   115|                    if new_opts - existing_opts:
   116|                        merged = list(existing_opts | new_opts)
   117|                        for idx, f in enumerate(new_schema):
   118|                            if f["name"] == fname:
   119|                                new_schema[idx] = {**f, "options": {**f.get("options", {}), "values": merged}}
   120|                                changed = True
   121|                                break
   122|            if changed:
   123|                await self._request(
   124|                    "PATCH",
   125|                    f"/api/collections/{existing_collection['id']}",
   126|                    json={"schema": new_schema},
   127|                )
   128|
   129|    async def ensure_default_webinar(self) -> None:
   130|        items = await self.list_records(
   131|            "webinars",
   132|            filter_='slug="laranko-remont-bez-haosu-2026-05-20"',
   133|            per_page=1,
   134|        )
   135|        if items:
   136|            return
   137|
   138|        from app.content import (
   139|            CONFIRMATION_TEXT,
   140|            WEBINAR_TITLE,
   141|            WELCOME_TEXT,
   142|            default_scheduled_messages,
   143|            default_webinar_datetime,
   144|        )
   145|
   146|        webinar_at = default_webinar_datetime(self.settings.timezone)
   147|        webinar = await self.create_record(
   148|            "webinars",
   149|            {
   150|                "slug": "laranko-remont-bez-haosu-2026-05-20",
   151|                "title": WEBINAR_TITLE,
   152|                "description": WELCOME_TEXT,
   153|                "confirmation_text": CONFIRMATION_TEXT,
   154|                "scheduled_at": webinar_at.isoformat(),
   155|                "timezone": self.settings.timezone,
   156|                "status": "published",
   157|                "zoom_url": self.settings.default_zoom_url,
   158|                "course_url": self.settings.default_course_url,
   159|                "instagram_ola_url": self.settings.instagram_ola_url,
   160|                "instagram_school_url": self.settings.instagram_school_url,
   161|                "instagram_studio_url": self.settings.instagram_studio_url,
   162|                "curator_username": self.settings.curator_username,
   163|            },
   164|        )
   165|        for template in default_scheduled_messages(webinar_at):
   166|            await self.create_record(
   167|                "scheduled_messages",
   168|                {
   169|                    "webinar": webinar["id"],
   170|                    "title": template.title,
   171|                    "text": template.text,
   172|                    "send_at": template.send_at.isoformat(),
   173|                    "buttons": [button.__dict__ for button in template.buttons],
   174|                    "media_type": template.media_type,
   175|                    "media_file_id": "",
   176|                    "media_file_ids": [],
   177|                    "status": "pending",
   178|                    "sent_at": "",
   179|                },
   180|            )
   181|
   182|    async def list_records(
   183|        self,
   184|        collection: str,
   185|        *,
   186|        filter_: str | None = None,
   187|        sort: str | None = None,
   188|        page: int = 1,
   189|        per_page: int = 50,
   190|        expand: str | None = None,
   191|    ) -> list[dict[str, Any]]:
   192|        params: dict[str, Any] = {"page": page, "perPage": per_page}
   193|        if filter_:
   194|            params["filter"] = filter_
   195|        if sort:
   196|            params["sort"] = sort
   197|        if expand:
   198|            params["expand"] = expand
   199|        data = await self._request("GET", f"/api/collections/{collection}/records", params=params)
   200|        return data.get("items", [])
   201|
   202|    async def list_all_records(
   203|        self,
   204|        collection: str,
   205|        *,
   206|        filter_: str | None = None,
   207|        sort: str | None = None,
   208|        expand: str | None = None,
   209|    ) -> list[dict[str, Any]]:
   210|        page = 1
   211|        items: list[dict[str, Any]] = []
   212|        while True:
   213|            batch = await self.list_records(
   214|                collection,
   215|                filter_=filter_,
   216|                sort=sort,
   217|                page=page,
   218|                per_page=200,
   219|                expand=expand,
   220|            )
   221|            items.extend(batch)
   222|            if len(batch) < 200:
   223|                return items
   224|            page += 1
   225|
   226|    async def create_record(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
   227|        return await self._request("POST", f"/api/collections/{collection}/records", json=data)
   228|
   229|    async def get_record(self, collection: str, record_id: str) -> dict[str, Any]:
   230|        return await self._request("GET", f"/api/collections/{collection}/records/{record_id}")
   231|
   232|    async def update_record(self, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
   233|        return await self._request(
   234|            "PATCH",
   235|            f"/api/collections/{collection}/records/{record_id}",
   236|            json=data,
   237|        )
   238|
   239|    async def upsert_user(self, tg_user: Any) -> dict[str, Any]:
   240|        telegram_id = str(tg_user.id)
   241|        users = await self.list_records(USER_COLLECTION, filter_=f'telegram_id="{telegram_id}"', per_page=1)
   242|        payload = {
   243|            "telegram_id": telegram_id,
   244|            "username": tg_user.username or "",
   245|            "first_name": tg_user.first_name or "",
   246|            "last_name": tg_user.last_name or "",
   247|            "language_code": tg_user.language_code or "",
   248|            "last_seen_at": datetime.now(timezone.utc).isoformat(),
   249|        }
   250|        if users:
   251|            return await self.update_record(USER_COLLECTION, users[0]["id"], payload)
   252|        payload["first_seen_at"] = payload["last_seen_at"]
   253|        return await self.create_record(USER_COLLECTION, payload)
   254|
   255|    async def attribution_by_token(self, token: str) -> dict[str, Any] | None:
   256|        if not token:
   257|            return None
   258|        items = await self.list_records("attribution_tokens", filter_=f'token="{token}"', per_page=1)
   259|        return items[0] if items else None
   260|
   261|    async def mark_attribution_started(
   262|        self,
   263|        attribution: dict[str, Any],
   264|        *,
   265|        user_id: str,
   266|        telegram_id: int | str,
   267|        event_id: str,
   268|    ) -> dict[str, Any]:
   269|        return await self.update_record(
   270|            "attribution_tokens",
   271|            attribution["id"],
   272|            {
   273|                "user": user_id,
   274|                "telegram_id": str(telegram_id),
   275|                "status": "started",
   276|                "started_at": datetime.now(timezone.utc).isoformat(),
   277|                "start_event_id": event_id,
   278|            },
   279|        )
   280|
   281|    async def latest_started_attribution_for_user(self, user_id: str) -> dict[str, Any] | None:
   282|        items = await self.list_records(
   283|            "attribution_tokens",
   284|            filter_=f'user="{user_id}" && status!="registered"',
   285|            sort="-started_at",
   286|            per_page=1,
   287|        )
   288|        return items[0] if items else None
   289|
   290|    async def mark_attribution_registered(self, attribution: dict[str, Any], *, event_id: str) -> dict[str, Any]:
   291|        return await self.update_record(
   292|            "attribution_tokens",
   293|            attribution["id"],
   294|            {
   295|                "status": "registered",
   296|                "registered_at": datetime.now(timezone.utc).isoformat(),
   297|                "registration_event_id": event_id,
   298|            },
   299|        )
   300|
   301|    async def active_webinar(self) -> dict[str, Any]:
   302|        webinars = await self.list_records(
   303|            "webinars",
   304|            filter_='status="published"',
   305|            sort="scheduled_at",
   306|            per_page=1,
   307|        )
   308|        if not webinars:
   309|            raise PocketBaseError("No published webinars found")
   310|        return webinars[0]
   311|
   312|    async def registration_for(self, user_id: str, webinar_id: str) -> dict[str, Any] | None:
   313|        registrations = await self.list_records(
   314|            "registrations",
   315|            filter_=f'user="{user_id}" && webinar="{webinar_id}"',
   316|            per_page=1,
   317|        )
   318|        return registrations[0] if registrations else None
   319|
   320|    async def save_registration(
   321|        self,
   322|        *,
   323|        user_id: str,
   324|        webinar_id: str,
   325|        answers: dict[str, Any],
   326|    ) -> dict[str, Any]:
   327|        payload = {
   328|            "user": user_id,
   329|            "webinar": webinar_id,
   330|            "name": answers.get("name", ""),
   331|            "phone": answers.get("phone", ""),
   332|            "answers": answers,
   333|            "status": "registered",
   334|            "registered_at": datetime.now(timezone.utc).isoformat(),
   335|        }
   336|        existing = await self.registration_for(user_id, webinar_id)
   337|        if existing:
   338|            return await self.update_record("registrations", existing["id"], payload)
   339|        return await self.create_record("registrations", payload)
   340|
   341|    async def pending_messages(self, now: datetime) -> list[dict[str, Any]]:
   342|        now_filter = format_pocketbase_datetime(now)
   343|        return await self.list_all_records(
   344|            "scheduled_messages",
   345|            filter_=f'status="pending" && send_at<="{now_filter}"',
   346|            sort="send_at",
   347|        )
   348|
   349|    async def registered_users_for_webinar(self, webinar_id: str) -> list[dict[str, Any]]:
   350|        registrations = await self.list_all_records(
   351|            "registrations",
   352|            filter_=f'webinar="{webinar_id}" && status="registered"',
   353|        )
   354|        for registration in registrations:
   355|            try:
   356|                registration["user_record"] = await self.get_record(USER_COLLECTION, registration["user"])
   357|            except PocketBaseError:
   358|                registration["user_record"] = {}
   359|        return registrations
   360|
   361|    async def log_broadcast(self, data: dict[str, Any]) -> dict[str, Any]:
   362|        return await self.create_record("broadcast_logs", data)
   363|
   364|    async def registrations_csv(self) -> bytes:
   365|        registrations = await self.list_all_records("registrations", sort="-registered_at")
   366|        output = io.StringIO()
   367|        writer = csv.writer(output)
   368|        writer.writerow(
   369|            [
   370|                "registered_at",
   371|                "webinar",
   372|                "telegram_id",
   373|                "username",
   374|                "name",
   375|                "phone",
   376|                "design_stage",
   377|                "realization_experience",
   378|                "speaker_question",
   379|            ]
   380|        )
   381|        user_cache: dict[str, dict[str, Any]] = {}
   382|        webinar_cache: dict[str, dict[str, Any]] = {}
   383|        for item in registrations:
   384|            user_id = item.get("user", "")
   385|            webinar_id = item.get("webinar", "")
   386|            if user_id and user_id not in user_cache:
   387|                user_cache[user_id] = await self.get_record(USER_COLLECTION, user_id)
   388|            if webinar_id and webinar_id not in webinar_cache:
   389|                webinar_cache[webinar_id] = await self.get_record("webinars", webinar_id)
   390|            user = user_cache.get(user_id, {})
   391|            webinar = webinar_cache.get(webinar_id, {})
   392|            answers = item.get("answers") or {}
   393|            if isinstance(answers, str):
   394|                answers = json.loads(answers)
   395|            writer.writerow(
   396|                [
   397|                    item.get("registered_at", ""),
   398|                    webinar.get("title", ""),
   399|                    user.get("telegram_id", ""),
   400|                    user.get("username", ""),
   401|                    item.get("name", ""),
   402|                    item.get("phone", ""),
   403|                    answers.get("design_stage", ""),
   404|                    answers.get("realization_experience", ""),
   405|                    answers.get("speaker_question", ""),
   406|                ]
   407|            )
   408|        return output.getvalue().encode("utf-8-sig")
   409|
   410|
   411|def collection_definitions() -> list[dict[str, Any]]:
   412|    definitions = [
   413|        {
   414|            "name": USER_COLLECTION,
   415|            "type": "base",
   416|            "system": False,
   417|            "schema": [
   418|                {"name": "telegram_id", "type": "text", "required": True, "options": {"maxSize": 64}},
   419|                {"name": "username", "type": "text", "required": False, "options": {}},
   420|                {"name": "first_name", "type": "text", "required": False, "options": {}},
   421|                {"name": "last_name", "type": "text", "required": False, "options": {}},
   422|                {"name": "language_code", "type": "text", "required": False, "options": {}},
   423|                {"name": "first_seen_at", "type": "date", "required": False, "options": {}},
   424|                {"name": "last_seen_at", "type": "date", "required": False, "options": {}},
   425|            ],
   426|            "indexes": ["CREATE UNIQUE INDEX idx_tg_users_telegram_id ON tg_users (telegram_id)"],
   427|        },
   428|        {
   429|            "name": "webinars",
   430|            "type": "base",
   431|            "system": False,
   432|            "schema": [
   433|                {"name": "slug", "type": "text", "required": True, "options": {}},
   434|                {"name": "title", "type": "text", "required": True, "options": {}},
   435|                {"name": "description", "type": "text", "required": False, "options": {}},
   436|                {"name": "confirmation_text", "type": "text", "required": False, "options": {}},
   437|                {"name": "scheduled_at", "type": "date", "required": True, "options": {}},
   438|                {"name": "timezone", "type": "text", "required": True, "options": {}},
   439|                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["draft", "published", "archived"]}},
   440|                {"name": "zoom_url", "type": "url", "required": False, "options": {}},
   441|                {"name": "course_url", "type": "url", "required": False, "options": {}},
   442|                {"name": "instagram_ola_url", "type": "url", "required": False, "options": {}},
   443|                {"name": "instagram_school_url", "type": "url", "required": False, "options": {}},
   444|                {"name": "instagram_studio_url", "type": "url", "required": False, "options": {}},
   445|                {"name": "curator_username", "type": "text", "required": False, "options": {}},
   446|            ],
   447|            "indexes": ["CREATE UNIQUE INDEX idx_webinars_slug ON webinars (slug)"],
   448|        },
   449|        {
   450|            "name": "registrations",
   451|            "type": "base",
   452|            "system": False,
   453|            "schema": [
   454|                {"name": "user", "type": "text", "required": True, "options": {}},
   455|                {"name": "webinar", "type": "text", "required": True, "options": {}},
   456|                {"name": "name", "type": "text", "required": True, "options": {}},
   457|                {"name": "phone", "type": "text", "required": True, "options": {}},
   458|                {"name": "answers", "type": "json", "required": False, "options": {}},
   459|                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["registered", "cancelled"]}},
   460|                {"name": "registered_at", "type": "date", "required": False, "options": {}},
   461|            ],
   462|            "indexes": [],
   463|        },
   464|        {
   465|            "name": "scheduled_messages",
   466|            "type": "base",
   467|            "system": False,
   468|            "schema": [
   469|                {"name": "webinar", "type": "text", "required": True, "options": {}},
   470|                {"name": "title", "type": "text", "required": True, "options": {}},
   471|                {"name": "text", "type": "text", "required": True, "options": {}},
   472|                {"name": "send_at", "type": "date", "required": True, "options": {}},
   473|                {"name": "buttons", "type": "json", "required": False, "options": {}},
   474|                {"name": "media_type", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["none", "photo", "video"]}},
   475|                {"name": "media_file_id", "type": "text", "required": False, "options": {}},
   476|                {"name": "media_file_ids", "type": "json", "required": False, "options": {}},
   477|                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["pending", "sending", "sent", "failed", "cancelled"]}},
   478|                {"name": "sent_at", "type": "date", "required": False, "options": {}},
   479|            ],
   480|            "indexes": [],
   481|        },
   482|        {
   483|            "name": "attribution_tokens",
   484|            "type": "base",
   485|            "system": False,
   486|            "schema": [
   487|                {"name": "token", "type": "text", "required": True, "options": {"maxSize": 64}},
   488|                {"name": "pixel_id", "type": "text", "required": False, "options": {}},
   489|                {"name": "fbclid", "type": "text", "required": False, "options": {}},
   490|                {"name": "fbc", "type": "text", "required": False, "options": {}},
   491|                {"name": "fbp", "type": "text", "required": False, "options": {}},
   492|                {"name": "utm", "type": "json", "required": False, "options": {}},
   493|                {"name": "source_url", "type": "text", "required": False, "options": {"maxSize": 5000}},
   494|                {"name": "referrer", "type": "text", "required": False, "options": {"maxSize": 5000}},
   495|                {"name": "user_agent", "type": "text", "required": False, "options": {"maxSize": 2000}},
   496|                {"name": "ip_address", "type": "text", "required": False, "options": {}},
   497|                {"name": "telegram_id", "type": "text", "required": False, "options": {}},
   498|                {"name": "user", "type": "text", "required": False, "options": {}},
   499|                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["created", "started", "registered"]}},
   500|                {"name": "start_event_id", "type": "text", "required": False, "options": {}},
   501|