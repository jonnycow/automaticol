import csv
import re
from pathlib import Path
from typing import Any
from playwright.async_api import Page
CSV_PATH = Path("data/messages.csv")
MESSAGE_PATTERN = re.compile(
    r"Mensaje enviado\s+"
    r"(?P<timestamp>.+?)\s+"
    r"por\s*:?\s*"
    r"(?P<sender>[^:]+):\s*"
    r"(?P<text>.*)$",
    re.DOTALL,
)
def parse_message_aria(
    aria_label: str,
) -> dict[str, str] | None:
    if not aria_label:
        return None
    if "Mensajes de la conversación con el título" in aria_label:
        return None
    aria_label = aria_label.replace(
        "Presionar Enter, ",
        "",
        1,
    ).strip()
    match = MESSAGE_PATTERN.search(aria_label)
    if not match:
        return None
    timestamp = match.group("timestamp").strip()
    sender = match.group("sender").strip()
    text = match.group("text").strip()
    # Evento automático de Facebook.
    if text.lower().startswith(
        f"{sender.lower()} inició este chat"
    ):
        return None
    return {
        "timestamp": timestamp,
        "sender": sender,
        "text": text,
        "raw": aria_label,
    }
def ensure_csv() -> None:
    CSV_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if CSV_PATH.exists():
        return
    with CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "buyer",
                "listing",
                "price",
                "timestamp",
                "sender",
                "message",
            ],
        )
        writer.writeheader()
def load_existing_messages() -> set[tuple[str, str, str]]:
    ensure_csv()
    existing: set[tuple[str, str, str]] = set()
    with CSV_PATH.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)
        for row in reader:
            key = (
                row.get("buyer", ""),
                row.get("timestamp", ""),
                row.get("message", ""),
            )
            existing.add(key)
    return existing
def save_messages(
    messages: list[dict[str, str]],
) -> int:
    ensure_csv()
    existing = load_existing_messages()
    new_count = 0
    with CSV_PATH.open(
        "a",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "buyer",
                "listing",
                "price",
                "timestamp",
                "sender",
                "message",
            ],
        )
        for message in messages:
            key = (
                message["buyer"],
                message["timestamp"],
                message["message"],
            )
            if key in existing:
                continue
            writer.writerow(message)
            existing.add(key)
            new_count += 1
    return new_count
async def extract_listing_and_price(
    page: Page,
) -> tuple[str | None, str | None]:
    """
    Busca la información del producto en la zona
    visible del chat.
    Facebook normalmente muestra algo como:
        Marketplace
        COP220,000 - Echo Dot ...
    Esta función NO modifica ni toca la detección
    de conversaciones.
    """
    listing = None
    price = None
    try:
        # -----------------------------------------------------
        # Buscamos elementos visibles que contengan COP.
        # -----------------------------------------------------
        candidates = page.locator(
            "div, span"
        )
        count = await candidates.count()
        possible_blocks: list[
            tuple[int, str]
        ] = []
        for index in range(count):
            try:
                element = candidates.nth(index)
                if not await element.is_visible():
                    continue
                text = (
                    await element.inner_text()
                ).strip()
                if not text:
                    continue
                if "COP" not in text.upper():
                    continue
                # Evitamos bloques gigantes.
                if len(text) > 500:
                    continue
                match = re.search(
                    r"COP\s?[\d.,]+",
                    text,
                    re.IGNORECASE,
                )
                if not match:
                    continue
                # Guardamos el tamaño.
                # Más pequeño normalmente significa
                # que estamos cerca del elemento real.
                possible_blocks.append(
                    (
                        len(text),
                        text,
                    )
                )
            except Exception:
                continue
        # -----------------------------------------------------
        # Ordenar por texto más pequeño.
        # -----------------------------------------------------
        possible_blocks.sort(
            key=lambda item: item[0]
        )
        for _, text in possible_blocks:
            price_match = re.search(
                r"COP\s?[\d.,]+",
                text,
                re.IGNORECASE,
            )
            if not price_match:
                continue
            price = price_match.group(0).strip()
            # Texto después del precio.
            remaining = text[
                price_match.end():
            ].strip()
            # Ejemplo:
            #
            # COP220,000 - Echo Dot...
            #
            if remaining.startswith("-"):
                remaining = (
                    remaining[1:]
                    .strip()
                )
            if remaining:
                first_line = (
                    remaining
                    .splitlines()[0]
                    .strip()
                )
                if first_line:
                    listing = first_line
            if price:
                break
    except Exception:
        pass
    return listing, price
async def extract_current_chat(
    page: Page,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "buyer": None,
        "listing": None,
        "price": None,
        "messages": [],
    }
    # =========================================================
    # PANEL DE CONVERSACIÓN
    # =========================================================
    panel = page.locator(
        '[aria-label*="Mensajes de la conversación"]'
    )
    if await panel.count() == 0:
        return result
    chat_panel = panel.first
    try:
        chat_text = await chat_panel.inner_text()
    except Exception:
        chat_text = ""
    # =========================================================
    # PRECIO / PUBLICACIÓN
    #
    # Primero intentamos el método anterior.
    # Si Facebook no los pone dentro del panel,
    # usamos la búsqueda visual.
    # =========================================================
    price_match = re.search(
        r"COP\s?[\d.,]+",
        chat_text,
        re.IGNORECASE,
    )
    if price_match:
        result["price"] = (
            price_match.group(0).strip()
        )
    listing_match = re.search(
        r"Marketplace\s+"
        r"COP\s?[\d.,]+\s*-\s*"
        r"(.+?)(?=\n|$)",
        chat_text,
        re.DOTALL,
    )
    if listing_match:
        result["listing"] = re.sub(
            r"\s+",
            " ",
            listing_match.group(1),
        ).strip()
    # ---------------------------------------------------------
    # Si el método anterior no encontró los datos,
    # buscamos en el DOM visible.
    # ---------------------------------------------------------
    if not result["price"] or not result["listing"]:
        listing, price = (
            await extract_listing_and_price(
                page
            )
        )
        if not result["price"]:
            result["price"] = price
        if not result["listing"]:
            result["listing"] = listing
    # =========================================================
    # MENSAJES
    # =========================================================
    elements = page.locator(
        '[aria-label*="Mensaje enviado"]'
    )
    count = await elements.count()
    messages: list[dict[str, str]] = []
    for index in range(count):
        try:
            aria_label = await elements.nth(
                index
            ).get_attribute("aria-label")
            if not aria_label:
                continue
            message = parse_message_aria(
                aria_label
            )
            if message is None:
                continue
            if any(
                existing["raw"] == message["raw"]
                for existing in messages
            ):
                continue
            messages.append(message)
        except Exception:
            continue
    result["messages"] = messages
    # =========================================================
    # COMPRADOR
    # =========================================================
    for message in messages:
        sender = message["sender"]
        if sender.lower() not in {
            "tú",
            "you",
        }:
            result["buyer"] = sender
            break
    return result
async def find_conversations(
    page: Page,
) -> list[str]:
    """
    DETECTOR ORIGINAL.
    No modificar esta parte mientras estamos
    corrigiendo la extracción.
    """
    conversations: list[str] = []
    candidates = page.locator(
        '[role="button"]'
    )
    count = await candidates.count()
    for index in range(count):
        try:
            text = (
                await candidates.nth(index)
                .inner_text()
            ).strip()
            if not text:
                continue
            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ]
            if not lines:
                continue
            name = lines[0]
            ignored = {
                "Marketplace",
                "Bandeja de entrada",
                "Compra",
                "Venta",
                "Notificaciones",
                "Explorar todo",
                "Crear publicación",
            }
            if name in ignored:
                continue
            if len(name) > 100:
                continue
            if name not in conversations:
                conversations.append(name)
        except Exception:
            continue
    return conversations
async def open_conversation(
    page: Page,
    buyer_name: str,
) -> bool:
    matches = page.get_by_text(
        buyer_name,
        exact=False,
    )
    count = await matches.count()
    if count == 0:
        return False
    for index in range(count):
        try:
            text = (
                await matches.nth(index)
                .inner_text()
            ).strip()
            if buyer_name.lower() not in text.lower():
                continue
            await matches.nth(index).click(
                position={
                    "x": 20,
                    "y": 20,
                },
                timeout=5000,
            )
            await page.wait_for_timeout(
                1200
            )
            return True
        except Exception:
            continue
    return False
async def open_marketplace(
    page: Page,
    base_url: str,
) -> None:
    # =========================================================
    # 1. ABRIR BANDEJA
    # =========================================================
    inbox_url = (
        f"{base_url.rstrip('/')}"
        "/marketplace/inbox/"
    )
    print()
    print("======================================")
    print("ABRIENDO MARKETPLACE")
    print("======================================")
    await page.goto(
        inbox_url,
        wait_until="domcontentloaded",
    )
    await page.wait_for_timeout(
        3000
    )
    print(
        "Bandeja de entrada abierta."
    )
    # =========================================================
    # 2. DETECTAR CONVERSACIONES
    # =========================================================
    print()
    print("======================================")
    print("BUSCANDO CONVERSACIONES")
    print("======================================")
    conversations = await find_conversations(
        page
    )
    print(
        f"Conversaciones detectadas: "
        f"{len(conversations)}"
    )
    if not conversations:
        print(
            "No se encontraron conversaciones."
        )
        return
    # =========================================================
    # 3. CSV
    # =========================================================
    ensure_csv()
    total_messages = 0
    total_new = 0
    # =========================================================
    # 4. PROCESAR
    # =========================================================
    for index, buyer_name in enumerate(
        conversations,
        start=1,
    ):
        print()
        print("--------------------------------------")
        print(
            f"[{index}/{len(conversations)}] "
            f"{buyer_name}"
        )
        print("--------------------------------------")
        opened = await open_conversation(
            page=page,
            buyer_name=buyer_name,
        )
        if not opened:
            print(
                "No se pudo abrir."
            )
            continue
        chat = await extract_current_chat(
            page
        )
        if not chat["buyer"]:
            print(
                "No se pudo identificar comprador."
            )
            continue
        messages_for_csv: list[
            dict[str, str]
        ] = []
        for message in chat["messages"]:
            messages_for_csv.append(
                {
                    "buyer": chat["buyer"],
                    "listing": (
                        chat["listing"] or ""
                    ),
                    "price": (
                        chat["price"] or ""
                    ),
                    "timestamp": (
                        message["timestamp"]
                    ),
                    "sender": (
                        message["sender"]
                    ),
                    "message": (
                        message["text"]
                    ),
                }
            )
        total_messages += (
            len(messages_for_csv)
        )
        new_count = save_messages(
            messages_for_csv
        )
        total_new += new_count
        print(
            f"Publicación: "
            f"{chat['listing']}"
        )
        print(
            f"Precio: "
            f"{chat['price']}"
        )
        print(
            f"Mensajes encontrados: "
            f"{len(messages_for_csv)}"
        )
        print(
            f"Mensajes nuevos en CSV: "
            f"{new_count}"
        )
        # Volver a la bandeja.
        await page.wait_for_timeout(
            500
        )
        await page.goto(
            inbox_url,
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(
            1200
        )
    # =========================================================
    # 5. RESUMEN
    # =========================================================
    print()
    print("======================================")
    print("PROCESAMIENTO TERMINADO")
    print("======================================")
    print(
        f"Conversaciones detectadas : "
        f"{len(conversations)}"
    )
    print(
        f"Mensajes procesados       : "
        f"{total_messages}"
    )
    print(
        f"Mensajes nuevos guardados : "
        f"{total_new}"
    )
    print()
    print(
        f"CSV: {CSV_PATH.resolve()}"
    )
    print()
    print(
        "No se ha enviado ningún mensaje."
    )
    print(
        "El navegador permanecerá abierto."
    )