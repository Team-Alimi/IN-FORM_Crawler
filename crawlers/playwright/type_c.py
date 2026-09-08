from common.utils import format_date_str, parse_date_raw

from .base import BaseCrawler


class TypeCCrawler(BaseCrawler):
    """카테고리 탭이 분리된 게시판(Type C)을 위한 Playwright 크롤러 구현체"""

    async def parse_list(self):
        """지정된 카테고리 탭들을 순회하며 각 목록 페이지를 파싱"""
        self.log(f"수집 시작 (기한: {self.limit.strftime('%Y-%m-%d')})", "START")
        for tid in [1, 3, 4]:
            self.log(f"Tab {tid} 진입...", "START")
            page_num, streak, prev_tits = 1, 0, []
            while True:
                sep = "&" if "?" in self.url else "?"
                url = f"{self.url}{sep}cate={tid}&page={page_num}"
                if not await self.safe_goto(url):
                    break

                try:
                    await self.page.wait_for_selector("tbody tr", timeout=5000)
                except:
                    break

                rows_loc = self.page.locator("tbody tr")
                rows_count = await rows_loc.count()
                if rows_count == 0:
                    break

                curr_tits = [
                    t.strip()
                    for t in (await self.page.locator("td.subject a").all_inner_texts())
                    if t.strip()
                ]
                if curr_tits and curr_tits == prev_tits:
                    break
                prev_tits = curr_tits

                for i in range(rows_count):
                    try:
                        row = self.page.locator(f"tbody tr >> nth={i}")
                        sub, reg = row.locator("td.subject"), row.locator("td.regdate")
                        if await sub.count() == 0 or await reg.count() == 0:
                            continue

                        title_a, dt_s = (
                            sub.locator("a").first,
                            reg.locator("span").first,
                        )
                        title, dt_txt = (
                            (await title_a.inner_text()).strip(),
                            (await dt_s.inner_text()).strip(),
                        )
                        if not dt_txt:
                            dt_txt = await dt_s.get_attribute("title") or ""

                        dt_obj = parse_date_raw(dt_txt)
                        if dt_obj is None:
                            continue

                        if dt_obj < self.limit:
                            streak += 1
                            if streak >= 20:
                                self.log(f"Tab {tid} 기한 도달.", "STOP")
                                break
                            continue
                        else:
                            streak = 0

                        native_post_id = (
                            (await row.locator("._artclTdNum").inner_text()).strip()
                            if await row.locator("._artclTdNum").count() > 0
                            else ""
                        )
                        if not native_post_id:
                            self.log(
                                "source-native identifier unavailable; skipped", "WARN"
                            )
                            continue

                        await title_a.scroll_into_view_if_needed()
                        await title_a.click(timeout=5000)
                        await self.page.wait_for_timeout(2000)

                        await self.parse_detail(title, dt_obj, native_post_id)

                        await self.page.go_back()
                        await self.page.wait_for_timeout(2000)
                    except Exception as e:
                        self.log(f"항목 처리 실패: {e}", "WARN")
                        await self.safe_goto(url)
                        await self.page.wait_for_timeout(2000)

                if streak >= 20:
                    break
                page_num += 1
                if page_num > 100:
                    break

    async def parse_detail(self, title, dt_obj, native_post_id):
        """상세 페이지에서 본문 및 첨부파일을 추출하고 부모 클래스의 정제 로직 호출"""
        view = self.page.locator(".contents_wrap, .artclView")
        if await view.count() == 0:
            return
        raw_html = (await view.first.inner_text()).strip()
        att = []
        for img in await view.locator("img").all():
            src = await img.get_attribute("src")
            if src:
                att.append(
                    {
                        "attachment_url": await self.page.evaluate(
                            "(src) => new URL(src, document.baseURI).href", src
                        )
                    }
                )

        if not raw_html and not att:
            return

        try:
            source_identity = self.build_source_identity(native_post_id, self.page.url)
        except ValueError:
            self.log("source-native identifier unavailable; skipped", "WARN")
            return

        self.process_item(
            {
                "unique_id": source_identity["external_key"],
                "title": title,
                "content": raw_html,
                "original_url": source_identity["source_url"],
                "created_at": format_date_str(dt_obj),
                "updated_at": format_date_str(dt_obj),
                "attachments": att,
                **source_identity,
            }
        )
