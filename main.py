import os
import time
import random
from datetime import datetime, timedelta, timezone
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# ==========================================
# 1. 初期設定とランダムアワードの抽選
# ==========================================
load_dotenv()
SLACK_TOKEN = os.environ.get("SLACK_TOKEN")
client = WebClient(token=SLACK_TOKEN)

TARGET_CHANNEL = "#times-猪田-timesランキング開発"

JST = timezone(timedelta(hours=+9), 'JST')
now = datetime.now(JST)
one_week_ago = now - timedelta(days=7)
two_weeks_ago = now - timedelta(days=14)

ts_one_week = one_week_ago.timestamp()
ts_two_weeks = two_weeks_ago.timestamp()

AWARDS_LIST = {
    "emoji": "絵文字コレクター賞🎨", "lone_wolf": "独り言マスター賞🐺", 
    "curiosity": "クエスチョン賞❓", "tech": "コード共有賞💻", 
    "news": "情報ハブ賞🔗", "visual": "メディアクリエイター賞📷", 
    "early": "朝活マスター賞🌅", "night": "深夜の番人賞🦉"
}

AWARDS_DESC = {
    "emoji": "色々な種類の絵文字でリアクションをもらった人です！",
    "lone_wolf": "誰からもリアクションや返信がつかなくてもめげずに発言した人です！",
    "curiosity": "発言の中に「？」が一番多く、たくさん質問や問題提起をした人です！",
    "tech": "コードブロック（```）を一番多く使い、技術的な共有をしてくれた人です！",
    "news": "URLを一番多く共有し、情報収集・発信に貢献してくれた人です！",
    "visual": "画像やファイルを一番多くアップロードしてくれた人です！",
    "early": "朝5時〜8時の間に一番多く発言した、早起きな人です！",
    "night": "深夜0時〜4時の間に一番多く発言した、夜更かし（？）な人です！"
}

weekly_random_award = random.choice(list(AWARDS_LIST.keys()))

# ==========================================
# 2. チャンネルの取得とグループ化
# ==========================================
print("チャンネル一覧を取得中...")
user_channels = {}

try:
    response = client.conversations_list(types="public_channel", limit=1000)
    for c in response["channels"]:
        channel_name = c["name"]
        if channel_name.startswith("times-"):
            name_parts = channel_name.split("-")
            if len(name_parts) >= 2:
                user_name = name_parts[1]
                if user_name not in user_channels:
                    user_channels[user_name] = []
                user_channels[user_name].append(c["id"])
except SlackApiError as e:
    print(f"一覧取得エラー: {e}")

# ==========================================
# 3. メッセージの取得とスコア集計
# ==========================================
print("過去2週間分のデータを解析中...（少し時間がかかります）")
user_stats = {}

for user_name, channel_ids in user_channels.items():
    stats = {
        "channel_id": channel_ids[0], # ★追加: リンク用に代表チャンネルのIDを保存
        "current_score": 0, "past_score": 0, "current_msgs": 0, "threads": 0,
        "reactions_count": 0,
        "emoji_types": set(), "lone_wolf": 0, "curiosity": 0, "tech": 0,
        "news": 0, "visual": 0, "early": 0, "night": 0
    }
    
    for channel_id in channel_ids:
        try:
            client.conversations_join(channel=channel_id)
        except SlackApiError as e:
            if e.response["error"] not in ["already_in_channel"]:
                continue

        try:
            history = client.conversations_history(channel=channel_id, oldest=str(ts_two_weeks), limit=500)
            
            for msg in history["messages"]:
                if "subtype" in msg: continue
                
                msg_ts = float(msg["ts"])
                msg_text = msg.get("text", "")
                msg_user = msg.get("user", "")
                reply_count = msg.get("reply_count", 0)
                
                if msg_ts < ts_one_week:
                    stats["past_score"] += 5 + (reply_count * 5)
                    if "reactions" in msg:
                        for r in msg["reactions"]:
                            if msg_user not in r.get("users", []):
                                stats["past_score"] += r["count"] * 2
                    continue
                
                msg_score = 5
                stats["current_msgs"] += 1
                stats["threads"] += reply_count
                msg_score += reply_count * 5
                
                reaction_count = 0
                if "reactions" in msg:
                    for r in msg["reactions"]:
                        valid_count = r["count"]
                        if msg_user in r.get("users", []):
                            valid_count -= 1
                        
                        if valid_count > 0:
                            msg_score += valid_count * 2
                            reaction_count += valid_count
                            stats["emoji_types"].add(r["name"])
                
                stats["reactions_count"] += reaction_count
                stats["current_score"] += msg_score
                
                if reply_count == 0 and reaction_count == 0: stats["lone_wolf"] += 1
                if "?" in msg_text or "？" in msg_text: stats["curiosity"] += 1
                if "```" in msg_text: stats["tech"] += 1
                if "http" in msg_text or "<http" in msg_text: stats["news"] += 1
                if "files" in msg: stats["visual"] += 1
                
                msg_hour = datetime.fromtimestamp(msg_ts, JST).hour
                if 5 <= msg_hour <= 8: stats["early"] += 1
                if 0 <= msg_hour <= 4: stats["night"] += 1

            time.sleep(1)
        except SlackApiError as e:
            print(f"取得エラー: {e}")
            
    user_stats[user_name] = stats

# ==========================================
# 4. ランキングの決定
# ==========================================
def get_winner(sort_key, min_msg=0, is_length=False):
    valid_users = {k: v for k, v in user_stats.items() if v["current_msgs"] >= min_msg}
    if not valid_users: return "該当者なし", 0
    if is_length:
        winner = max(valid_users.items(), key=lambda x: len(x[1][sort_key]))
        return winner[0], len(winner[1][sort_key])
    else:
        winner = max(valid_users.items(), key=lambda x: x[1][sort_key])
        return winner[0], winner[1][sort_key]

# リンク生成用ヘルパー関数
def get_user_link(name):
    if name == "該当者なし": return name
    return f"<#{user_stats[name]['channel_id']}>"

sorted_overall = sorted(user_stats.items(), key=lambda x: x[1]["current_score"], reverse=True)

for k, v in user_stats.items(): v["growth"] = v["current_score"] - v["past_score"]
growth_winner, growth_val = get_winner("growth")

for k, v in user_stats.items(): v["thread_ratio"] = (v["threads"] / v["current_msgs"]) * 100 if v["current_msgs"] > 0 else 0
thread_winner, thread_val = get_winner("thread_ratio", min_msg=3)

random_award_name = AWARDS_LIST[weekly_random_award]
random_award_desc = AWARDS_DESC[weekly_random_award]
if weekly_random_award == "emoji":
    rand_winner, rand_val = get_winner("emoji_types", is_length=True)
else:
    rand_winner, rand_val = get_winner(weekly_random_award)

# ==========================================
# 5. メッセージの組み立て
# ==========================================
slack_msg = "==============================\n"
slack_msg += "🎉 *今週のtimes盛り上がりランキング* 🎉\n"
slack_msg += "==============================\n\n"

slack_msg += "👑 *【総合ランキング トップ3】*\n"
for i, (name, stats) in enumerate(sorted_overall[:3]):
    # ★「さん」を消して、<#ID> 形式に変更
    slack_msg += f"第{i+1}位: <#{stats['channel_id']}>\n"
    slack_msg += f"　総合スコア: {stats['current_score']}pt (発言: {stats['current_msgs']}回 / 返信: {stats['threads']}回 / リアクション: {stats['reactions_count']}回)\n\n"

slack_msg += "*今週のピックアップ*\n\n"
slack_msg += f"🚀急上昇賞: {get_user_link(growth_winner)} (先週比: +{growth_val}pt)\n\n"
slack_msg += f"📚議論メーカー賞: {get_user_link(thread_winner)} (スレッド化率: {thread_val:.1f}%)\n\n"
slack_msg += f"🎲{random_award_name}: {get_user_link(rand_winner)} (記録: {rand_val})\n"
slack_msg += f"　💬 {random_award_desc}\n"

# ==========================================
# ▼ モードB：本番用（Slackに送信する）
# ==========================================

"""
# --------------------------------------------------
# ▼ モードA：テスト用（ターミナルに表示するだけ）
# --------------------------------------------------
print("\n▼ 送信予定のメッセージ ▼\n")
print(slack_msg)
print("\n※ 現在はテストモードのため、Slackには送信されていません。")
"""

# --------------------------------------------------
# ▼ モードB：本番用（Slackに送信する）
# 本番稼働時は、下の """ （2箇所）を消して有効化してください。
# --------------------------------------------------

try:
    print("\nSlackに送信しています...")
    client.chat_postMessage(
        channel=TARGET_CHANNEL,
        text=slack_msg
    )
    print(f"✅ {TARGET_CHANNEL} への送信が完了しました！")
except SlackApiError as e:
    print(f"⚠️ 送信エラーが発生しました: {e.response['error']}")
