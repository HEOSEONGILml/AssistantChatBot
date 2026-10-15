"""기분별 임시 스프라이트 시트를 만든다 (기분별 그림 스펙).

원본 시트의 모든 프레임에서 눈(밝은 픽셀 하나)을 찾고, 눈 위치를 기준으로 기분별 얼굴(눈·눈썹·볼·혀·눈물·땀)을
픽셀로 덧그린다. 그래서 모든 동작×기분 조합이 생긴다. 눈이 없는 프레임(잠)은 그대로 둔다.
진짜 그림이 생기면 이 파일 대신 그림 파일을 manifest의 `moods`에 넣으면 된다.

실행 (`app/`에서): uv run --with pillow python tools/draw_moods.py
"""
from pathlib import Path

from PIL import Image

DIR = Path(__file__).resolve().parent.parent / "public" / "sprites" / "dog"
BASE = "dog-02"
FW, FH = 64, 48

K = (20, 16, 19, 255)      # 윤곽선 (원본 팔레트)
W = (227, 230, 255, 255)   # 눈 흰자 (원본 팔레트)
FUR = (187, 117, 71, 255)  # 털 (원본 팔레트)
PINK = (240, 120, 150, 255)
TONGUE = (226, 92, 110, 255)
BLUE = (120, 180, 245, 255)
RED = (225, 40, 40, 255)

# 눈 하이라이트(ex, ey) 기준 상대 좌표. 시트의 강아지는 왼쪽(주둥이 쪽 = x 감소)을 본다.
# 눈동자는 (−1, 0), 눈썹 자리는 y −1~−2, 볼은 y +2, 머리 꼭대기 윤곽은 y −3.
FACES: dict[str, list[tuple[int, int, tuple]]] = {
    # 행복: 눈웃음(^)과 분홍 볼
    "happy": [(-1, 0, FUR), (-2, 0, K), (-1, -1, K), (0, 0, K), (-1, 2, PINK), (0, 2, PINK)],
    # 신남: 크고 반짝이는 눈, 혀
    "excited": [(-1, -1, K), (0, -1, W), (-1, 0, K), (0, 0, K), (-5, 5, TONGUE), (-4, 5, TONGUE), (-5, 6, TONGUE)],
    # 서운함: 안쪽이 올라간 처진 눈썹, 눈물
    "sad": [(-2, -2, K), (-1, -1, K), (0, 0, K), (-1, 1, BLUE), (-1, 2, BLUE)],
    # 짜증: 안쪽이 내려간 눈썹, 머리 위 핏줄
    "annoyed": [(-2, -1, K), (-1, -1, K), (0, -2, K), (2, -7, RED), (1, -6, RED), (3, -6, RED), (2, -5, RED)],
    # 졸림: 감은 눈
    "sleepy": [(-2, 0, K), (-1, 0, K), (0, 0, K), (-1, -1, FUR), (0, -1, FUR)],
    # 심심함: 반쯤 감긴 눈
    "bored": [(-2, -1, K), (-1, -1, K), (0, -1, K)],
    # 궁금함: 위아래로 커진 눈, 올라간 눈썹
    "curious": [(-1, -1, K), (0, -1, W), (0, -3, K), (1, -3, K)],
    # 놀람: 흰자에 둘러싸인 눈동자
    "surprised": [(-2, 0, W), (0, 0, W), (-1, -1, W), (-1, 1, W), (-1, 0, K)],
    # 무서움: 흰자가 보이는 눈, 걱정 눈썹, 땀방울
    "scared": [(-2, 0, W), (0, 0, W), (-1, -1, W), (-2, -2, K), (-1, -2, K), (6, -4, BLUE), (6, -3, BLUE), (7, -3, BLUE)],
}


def eye(frame: Image.Image) -> tuple[int, int] | None:
    found = [(x, y) for y in range(FH) for x in range(FW)
             if (p := frame.getpixel((x, y)))[3] and min(p[:3]) > 170]
    assert len(found) <= 1, found
    return found[0] if found else None


def draw(sheet: Image.Image, face: list[tuple[int, int, tuple]]) -> Image.Image:
    out = sheet.copy()
    for top in range(0, sheet.height, FH):
        for left in range(0, sheet.width, FW):
            e = eye(sheet.crop((left, top, left + FW, top + FH)))
            if e is None:
                continue
            for dx, dy, color in face:
                x, y = e[0] + dx, e[1] + dy
                if 0 <= x < FW and 0 <= y < FH:
                    out.putpixel((left + x, top + y), color)
    return out


def main() -> None:
    sheet = Image.open(DIR / f"{BASE}.png").convert("RGBA")
    for mood, face in FACES.items():
        draw(sheet, face).save(DIR / f"{BASE}-{mood}.png")
        print(f"{BASE}-{mood}.png")


if __name__ == "__main__":
    main()
