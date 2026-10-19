# 웹 프로토타입 구현 계획

스펙: [웹 프로토타입](../specs/2026-10-19-web-prototype-design.md). 프로토타입이라 계획은 짧게 둔다. 순수 로직은 테스트를 먼저 쓴다.

1. **두뇌 설정**: `config.read_keys`가 자격 저장소에 없으면 `TYPESAFE_API_KEY`·`GEMINI_API_KEY`를 읽는다. `config.web_data_dir()`. 테스트: `brain/tests/test_config.py`.
2. **두뇌 웹 모드**: `brain/brain/web.py`.
   - 순수 함수 `static_path(root, url_path)`(폴더 밖이면 None), `same_origin(origin, host)`. 테스트: `brain/tests/test_web.py`.
   - `process_request`: `/token` → JSON, `/ws` → 출처 검사 뒤 WebSocket(기존 `Link.handler`), 그 밖 → 정적 파일.
   - `main()`: 인자 `--host`·`--port`·`--static`. 실제 서버로 GET `/`, `/token`, WS hello까지 붙는 통합 테스트 하나.
3. **웹 화면 순수 로직**: `app/src/web/endpoint.ts`, `presence.ts`, `prefs.ts`. 테스트: `app/tests/web-*.test.ts`.
4. **웹 화면 조립**: `app/web.html`, `app/src/web/main.ts`(그리기·입력·이벤트·두뇌 연결), `app/src/web/link.ts`(같은 출처 접속·재접속), 설정 패널. `vite.web.config.ts`, `npm run build:web` → `app/dist-web/`.
5. **확인**: 두뇌·화면 테스트, 타입 검사, 빌드. 웹 모드를 띄워 브라우저(chrome-devtools)로 강아지·말 걸기·찌르기를 확인한다. `docs/manual-checks/web.md`.
6. **문서 동기화**: README(실행), ARCHITECTURE(구성 요소·저장과 실행·코드 지도·문서 지도·결정 기록), `docs/brain-protocol.md`(웹 모드 접속), glossary(웹 모드).
