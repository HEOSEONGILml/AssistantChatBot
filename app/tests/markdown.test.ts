import { describe, expect, it } from "vitest";
import { parseMarkdown } from "../src/shared/markdown";

const t = (v: string) => ({ t: "text", v });

describe("parseMarkdown", () => {
  it("빈 줄로 문단을 나누고, 문단 안 줄바꿈은 줄로 남긴다", () => {
    expect(parseMarkdown("가\n나\n\n다")).toEqual([
      { type: "p", lines: [[t("가")], [t("나")]] },
      { type: "p", lines: [[t("다")]] },
    ]);
  });

  it("굵게와 인라인 코드", () => {
    expect(parseMarkdown("지금은 **오전 9시**예요. `ls -a` 실행")).toEqual([
      { type: "p", lines: [[t("지금은 "), { t: "b", v: "오전 9시" }, t("예요. "), { t: "code", v: "ls -a" }, t(" 실행")]] },
    ]);
  });

  it("글머리 목록(- , * )과 번호 목록", () => {
    expect(parseMarkdown("예:\n- 하나\n* **둘**\n1. 첫째\n2. 둘째\n끝")).toEqual([
      { type: "p", lines: [[t("예:")]] },
      { type: "ul", items: [[t("하나")], [{ t: "b", v: "둘" }]] },
      { type: "ol", items: [[t("첫째")], [t("둘째")]] },
      { type: "p", lines: [[t("끝")]] },
    ]);
  });

  it("그 밖의 문법은 글 그대로", () => {
    expect(parseMarkdown("# 제목 [링크](http://x) *기울임* **안 닫힘")).toEqual([
      { type: "p", lines: [[t("# 제목 [링크](http://x) *기울임* **안 닫힘")]] },
    ]);
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("-붙음")).toEqual([{ type: "p", lines: [[t("-붙음")]] }]);
  });
});
