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

PREFIX = "!partida"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


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


def fmt_partida(data: dict) -> str:
    ok = data.get("ok", False)
    if not ok:
        return "❌ Respuesta de n8n sin ok=true."

    inserted_id = data.get("insertedId") or "(sin id)"
    partida_raw = data.get("partida")

    if partida_raw is None:
        return "⚠️ No se recibió la partida desde n8n."

    if isinstance(partida_raw, str):
        try:
            partida = json.loads(partida_raw)
            if isinstance(partida, str):
                partida = json.loads(partida)
        except json.JSONDecodeError as e:
            return f"❌ Error decodificando la partida: {e}\nRaw: {partida_raw[:300]}"
    else:
        partida = partida_raw

    nombre = partida.get("nombrePartida", "(sin nombre)")
    max_j = partida.get("maxJugadores")
    jugadores = partida.get("jugadores", [])

    max_txt = str(max_j) if max_j is not None else "(sin max)"
    jug_txt = ", ".join(jugadores) if jugadores else "(sin jugadores)"

    return (
        f"✅ Partida creada correctamente\n"
        f"🆔 ID: {inserted_id}\n"
        f"📌 Nombre: {nombre}\n"
        f"👥 Jugadores ({len(jugadores)}/{max_txt}): {jug_txt}"
    )


@client.event
async def on_ready():
    print(f"Conectado como {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()

    if not content.lower().startswith(PREFIX):
        return

    user_text = content[len(PREFIX):].strip()
    if not user_text:
        await message.channel.send("ℹ️ Escribe algo: `!partida crea una partida llamada ...`")
        return

    payload = {
        "text": user_text,
        "usuarioDiscord": str(message.author.id),
        "canalId": str(message.channel.id),
        "mensajeId": str(message.id),
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
            msg or "⚠️ n8n respondió vacío. Revisa el nodo 'Respond to Webhook' (Respond With: Text o JSON válido)."
        )
        return

    await message.channel.send(fmt_partida(data))


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
