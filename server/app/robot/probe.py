import json

from ..config import settings
from ..services.bilibili_robot import AT_FEED_URL, FOLLOWERS_URL, BiliRobotClient


def main() -> None:
    client = BiliRobotClient(
        cookie={
            "SESSDATA": settings.robot_sessdata,
            "bili_jct": settings.robot_bili_jct,
            "DedeUserID": settings.robot_dedeuserid,
            "buvid3": settings.robot_buvid3,
            "buvid4": settings.robot_buvid4,
        },
        robot_uid=settings.robot_uid,
    )
    try:
        status, body = client.raw_response(
            FOLLOWERS_URL, params={"vmid": settings.robot_uid, "pn": 1, "ps": 50}
        )
        print(f"=== followers HTTP {status} ===")
        print(body)
        print("=== followers normalized ===")
        try:
            print(json.dumps(client.get_followers(), ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"解析失败：{exc}")

        status, body = client.raw_response(AT_FEED_URL)
        print(f"=== at feed HTTP {status} ===")
        print(body)
        print("=== at normalized ===")
        try:
            print(json.dumps(client.get_at_notifications(), ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"解析失败：{exc}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
