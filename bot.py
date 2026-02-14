import os
import asyncio
import aiohttp
import discord
import json

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "PON_AQUI_TU_TOKEN")
N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL",
    "http://45.147.251.186:5678/webhook/discord-query"
)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

COMMANDS = {
    "!create": "create",
    "!search": "search",
    "!update": "update",
    "!delete": "delete",
}

HELP_TEXT = (
    "ℹ️ Comandos:\n"
    "• `!create <texto>` → crea una partida\n"
    "• `!search <texto>` → busca partidas\n"
    "• `!update <texto>` → actualiza una partida\n"
    "• `!delete <texto>` → borra una partida\n\n"
    "Ejemplos:\n"
    "• `!create crea una partida llamada Valorant mañana a las 19 para 5`\n"
    "• `!search partidas con sitio`\n"
    "• `!search llamada \"Valorant\"`\n"
)

async def call_n8n(payload: dict, timeout_sec: int = 60):
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(N8N_WEBHOOK_URL, json=payload) as resp:
            status = resp.status
            text = await resp.text()

            if not text.strip():
                return status, None, ""

            try:
                data = await resp.json()
                return status, data, text
            except Exception:
                return status, None, text


def _pick(doc: dict, *keys, default=None):
    for k in keys:
        if k in doc and doc[k] is not None:
            return doc[k]
    return default


def fmt_response(data: dict, fallback_action: str | None = None) -> str:
    ok = data.get("ok", False)
    if not ok:
        err = data.get("error") or "Respuesta de n8n sin ok=true."
        return f"❌ {err}"

    action = data.get("action") or fallback_action or "(acción desconocida)"

    # CREATE
    if action == "create":
        inserted_id = data.get("insertedId") or data.get("id") or "(sin id)"
        doc = data.get("document") or data.get("partida") or data.get("game")
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except Exception:
                doc = None

        if not isinstance(doc, dict):
            return f"✅ Partida creada\n🆔 ID: {inserted_id}\n⚠️ (No llegó el documento para mostrar)"

        nombre = _pick(doc, "gameName", "nombrePartida", default="(sin nombre)")
        max_j = _pick(doc, "maxPlayers", "maxJugadores", default=None)
        creator = _pick(doc, "creator", "creator", default=None)
        players = _pick(doc, "players", "jugadores", default=[])
        if not isinstance(players, list):
            players = []

        max_txt = str(max_j) if max_j is not None else "(sin max)"
        jug_txt = ", ".join(map(str, players)) if players else "(sin jugadores)"

        return (
            f"✅ Partida creada correctamente\n"
            f"🆔 ID: {inserted_id}\n"
            f"📌 Nombre: {nombre}\n"
            f"👑 Host de la sala: {creator}\n"
            f"👥 Jugadores ({len(players)}/{max_txt}): {jug_txt}"
        )

    # SEARCH
    if action == "search":
        results = data.get("results") or data.get("documents") or data.get("items") or []
        if isinstance(results, str):
            try:
                results = json.loads(results)
            except Exception:
                results = []

        if not isinstance(results, list) or len(results) == 0:
            return "🔎 No encontré partidas con esos filtros."

        limit = min(len(results), 10)
        lines = [f"🔎 Encontradas {len(results)} partidas (mostrando {limit}):"]

        for i in range(limit):
            doc = results[i]
            if not isinstance(doc, dict):
                continue

            _id = str(doc.get("_id", "(sin id)"))
            nombre = _pick(doc, "gameName", "nombrePartida", default="(sin nombre)")
            max_j = _pick(doc, "maxPlayers", "maxJugadores", default=None)
            players = _pick(doc, "players", "jugadores", default=[])
            if not isinstance(players, list):
                players = []
            max_txt = str(max_j) if max_j is not None else "?"

            lines.append(f"• `{_id}` — {nombre} ({len(players)}/{max_txt})")

        msg = "\n".join(lines)
        # Discord límite 2000 chars
        return msg[:1900] + ("…" if len(msg) > 1900 else "")

    # UPDATE
    if action == "update":
        matched = data.get("matchedCount", data.get("matched", 0))
        modified = data.get("modifiedCount", data.get("modified", 0))
        return f"🛠️ Update hecho\n✅ Matched: {matched}\n✏️ Modified: {modified}"

    # DELETE
    if action == "delete":
        deleted = data.get("deletedCount", data.get("deleted", 0))
        return f"🗑️ Delete hecho\n✅ Deleted: {deleted}"

    return f"✅ OK ({action})"


def parse_command(content: str):
    # Devuelve (action, text) o (None, None)
    content = content.strip()
    lower = content.lower()
    for cmd, action in COMMANDS.items():
        if lower.startswith(cmd):
            rest = content[len(cmd):].strip()
            return action, rest
    return None, None


@client.event
async def on_ready():
    print(f"Conectado como {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    action, user_text = parse_command(content)

    if action is None:
        return

    # Para search permitimos vacío (ej: !search) → mostrar algo por defecto en n8n
    if action != "search" and not user_text:
        await message.channel.send("ℹ️ Te falta el texto.\n\n" + HELP_TEXT)
        return

    payload = {
        "action": action,
        "text": user_text or "",
        "userName": str(message.author.name),
    }

    try:
        status, data, raw_text = await call_n8n(payload, timeout_sec=90)
    except asyncio.TimeoutError:
        await message.channel.send("❌ Error llamando a n8n: TimeoutError")
        return
    except Exception as e:
        await message.channel.send(f"❌ Error llamando a n8n: {type(e).__name__}: {e}")
        return

    if data is None:
        msg = raw_text.strip()
        await message.channel.send(
            msg or "⚠️ n8n respondió vacío. Revisa el nodo 'Respond to Webhook' (JSON válido)."
        )
        return

    await message.channel.send(fmt_response(data, fallback_action=action))


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
