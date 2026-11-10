"""Client GraphQL asincrono per il backend Grohm (https://api.grohm.it/graphql).

Ricavato dal reverse engineering usato dall'app my-Grohm (lib/api/grohm_api.dart):
- autenticazione a cookie di sessione (Django), niente token;
- tutto passa da un'unica POST GraphQL;
- nessuna subscription: lo stato "live" si ottiene col polling di `device(id)`.

Il modulo non importa nulla di Home Assistant, così è testabile da solo.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

ENDPOINT = "https://api.grohm.it/graphql"

# Tipi account (User.accountType, arriva come stringa dal server).
ACCOUNT_PRIVATO = "0"
ACCOUNT_GESTORE = "1"
ACCOUNT_INSTALLATORE = "2"
SUPPORTED_ACCOUNT_TYPES = (ACCOUNT_PRIVATO, ACCOUNT_GESTORE)

# Stati della ricarica (DeviceLog.status).
STATUS_READY = "READY"
STATUS_CHARGING = "CHARGING"
STATUS_FINISHED = "FINISHED"
STATUS_PAUSED = "PAUSED"
STATUS_WAITING = "WAITING"
KNOWN_STATUSES = (
    STATUS_READY,
    STATUS_CHARGING,
    STATUS_FINISHED,
    STATUS_PAUSED,
    STATUS_WAITING,
)

_PAGE_SIZE = 50
_MAX_PAGES = 50
_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


class GrohmError(Exception):
    """Errore generico verso il backend."""


class GrohmConnectionError(GrohmError):
    """Server irraggiungibile, timeout o risposta non valida."""


class GrohmAuthError(GrohmError):
    """Credenziali errate o sessione scaduta che non si riesce a rinnovare."""


class GrohmUnsupportedAccountError(GrohmError):
    """Account di tipo non ammesso (installatore o tipo non impostato)."""

    def __init__(self, account_type: str | None) -> None:
        super().__init__(f"Tipo di account non supportato: {account_type!r}")
        self.account_type = account_type


# ============================ QUERY ============================

LOGIN_MUTATION = """
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) {
    __typename
    ... on LoginSuccess { user { id email firstName lastName accountType } }
    ... on LoginError { message }
  }
}
"""

ME_QUERY = """
query Me { me { id email firstName lastName accountType } }
"""

LOGOUT_MUTATION = "mutation Logout { logout }"

MY_DEVICES_QUERY = """
query MyDevices($page: Int!, $first: Int!) {
  myDevices(page: $page, first: $first) {
    items { id }
    pageInfo { hasNextPage nextPage }
  }
}
"""

# Le reti servono SOLO per scoprire le wallbox di un gestore: le reti in sé
# non vengono esposte in Home Assistant.
MY_NETWORKS_DEVICES_QUERY = """
query MyNetworksDevices($page: Int!, $first: Int!) {
  myNetworks(page: $page, first: $first) {
    items { devices { id } }
    pageInfo { hasNextPage nextPage }
  }
}
"""

DEVICES_OUT_OF_NET_QUERY = """
query DevicesOutOfNet($page: Int!, $first: Int!) {
  devicesOutOfNet(page: $page, first: $first) {
    items { id }
    pageInfo { hasNextPage nextPage }
  }
}
"""

DEVICE_FIELDS = """
fragment GrohmDevice on Device {
  id
  name
  serialNumber
  isConnected
  locked
  fase
  forceCharge
  hourCost
  maxPowerKw
  totalKwhCharged
  currentSession {
    status
    voltage
    maxCurrent
    maxCurrentCar
    wattHoursCharged
    energyCar
    chargeSeconds
    wifiPower
    createdAt
  }
}
"""

CHANGE_STATUS_MUTATION = """
mutation ChangeDeviceStatus($deviceId: ID!, $status: ChangeDeviceStatus!) {
  changeDeviceStatus(deviceId: $deviceId, status: $status) {
    device { id currentSession { status } }
  }
}
"""

EDIT_DEVICE_MUTATION = """
mutation EditDevice($id: ID!, $input: EditDeviceInput!) {
  editDevice(id: $id, input: $input) {
    __typename
    ... on EditDeviceSuccess { device { id } }
    ... on EditDeviceError { message }
  }
}
"""

NOTIFY_VIEWING_MUTATION = """
mutation NotifyViewing($id: ID!) {
  notifyDevice(id: $id, action: VIEWING) { device { id } }
}
"""


def build_devices_query(count: int) -> str:
    """Una sola query con alias (d0, d1, ...) per leggere N wallbox insieme."""
    params = ", ".join(f"$id{i}: ID!" for i in range(count))
    body = "\n".join(
        f"  d{i}: device(id: $id{i}) {{ ...GrohmDevice }}" for i in range(count)
    )
    return f"query Devices({params}) {{\n{body}\n}}\n{DEVICE_FIELDS}"


# ============================ HELPER DI DOMINIO ============================
# Stesse regole dell'app (grohm_api.dart), così HA mostra gli stessi numeri.

_TAGLI_MONO = (7.4,)
_TAGLI_TRI = (11.0, 22.0)


def is_three_phase(device: dict[str, Any]) -> bool:
    """`fase` vale "mono" o "tri"; qualunque altro valore è trattato da monofase."""
    return device.get("fase") == "tri"


def nominal_kw(device: dict[str, Any]) -> float | None:
    """Potenza nominale agganciata al taglio commerciale (7.4 / 11 / 22 kW)."""
    raw = device.get("maxPowerKw")
    if raw is None:
        return None
    try:
        kw = float(raw)
    except (TypeError, ValueError):
        return None
    best, best_dist = kw, math.inf
    for cut in _TAGLI_TRI if is_three_phase(device) else _TAGLI_MONO:
        dist = abs(kw - cut)
        if dist < best_dist and dist <= 1.0:
            best, best_dist = cut, dist
    return best


def voltage_volts(session: dict[str, Any] | None) -> float | None:
    """`voltage` arriva come STRINGA in millivolt."""
    raw = (session or {}).get("voltage")
    if raw is None:
        return None
    try:
        return int(str(raw)) / 1000.0
    except ValueError:
        return None


def power_w(session: dict[str, Any] | None) -> float | None:
    """Potenza istantanea in W dal campo `energyCar` (nome ingannevole: è una
    potenza). Fuori ricarica la wallbox riporta un residuo: senza CHARGING o con
    0 A all'auto la potenza è 0."""
    session = session or {}
    raw = session.get("energyCar")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if session.get("status") != STATUS_CHARGING or session.get("maxCurrentCar") == 0:
        return 0.0
    return value


def charging_phases(
    session: dict[str, Any] | None, device: dict[str, Any]
) -> int | None:
    """Fasi usate davvero dall'auto (1-3), solo per wallbox trifase in ricarica."""
    if not is_three_phase(device):
        return None
    power = power_w(session)
    amps = (session or {}).get("maxCurrentCar")
    if not power or power <= 0 or not amps or amps <= 0:
        return None
    volts = voltage_volts(session)
    if volts is None or not 180 <= volts <= 270:
        volts = 230.0
    return max(1, min(3, round(power / (volts * float(amps)))))


def pause_resume_target(status: str | None) -> str | None:
    """Comando changeDeviceStatus come nella webapp:
    CHARGING→PAUSED, PAUSED→RUNNING, WAITING→RESUMED (RESUMED da pausa non fa nulla)."""
    return {
        STATUS_CHARGING: "PAUSED",
        STATUS_PAUSED: "RUNNING",
        STATUS_WAITING: "RESUMED",
    }.get(status or "")


# ============================ CLIENT ============================


def create_session(ssl_context: Any = None) -> aiohttp.ClientSession:
    """Sessione HTTP dedicata con cookie jar proprio: il cookie di sessione
    Grohm è la credenziale dell'account e non deve finire in un jar condiviso
    (né mescolarsi tra due account configurati)."""
    connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None
    return aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), connector=connector)


@dataclass
class GrohmUser:
    """Utente autenticato."""

    id: str
    email: str
    account_type: str | None
    first_name: str | None = None
    last_name: str | None = None

    @property
    def is_gestore(self) -> bool:
        return self.account_type == ACCOUNT_GESTORE

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> GrohmUser:
        raw_type = data.get("accountType")
        return cls(
            id=str(data.get("id")),
            email=str(data.get("email") or ""),
            account_type=None if raw_type is None else str(raw_type),
            first_name=data.get("firstName"),
            last_name=data.get("lastName"),
        )


def ensure_supported(user: GrohmUser) -> None:
    """Solo privato e gestore. Gli installatori (e gli account senza tipo,
    creati dalla webapp e mai completati) non possono accedere."""
    if user.account_type not in SUPPORTED_ACCOUNT_TYPES:
        raise GrohmUnsupportedAccountError(user.account_type)


class GrohmApi:
    """Accesso al backend. Rifà il login da solo se la sessione scade."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        endpoint: str = ENDPOINT,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._endpoint = endpoint
        self._login_lock = asyncio.Lock()
        self.user: GrohmUser | None = None

    # ---------------------- trasporto ----------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # Il backend è Django: se c'è un csrftoken lo rispediamo nell'header
        # (innocuo se non serve), come fa l'app.
        for cookie in self._session.cookie_jar:
            if cookie.key == "csrftoken" and cookie.value:
                headers["X-CSRFToken"] = cookie.value
                headers["Referer"] = self._endpoint
        return headers

    async def _post(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Esegue una POST GraphQL e ritorna `data`. Lancia GrohmAuthError su
        401/403 o su errori GraphQL di autenticazione."""
        try:
            async with self._session.post(
                self._endpoint,
                json={"query": query, "variables": variables or {}},
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise GrohmAuthError(f"HTTP {resp.status}")
                if resp.status >= 500:
                    raise GrohmConnectionError(f"HTTP {resp.status}")
                try:
                    body = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise GrohmConnectionError("Risposta non JSON") from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise GrohmConnectionError(str(err) or type(err).__name__) from err

        if not isinstance(body, dict):
            raise GrohmConnectionError("Risposta non valida")
        data = body.get("data")
        errors = body.get("errors") or []
        if errors:
            message = "; ".join(str(e.get("message", e)) for e in errors)
            _LOGGER.debug("Errori GraphQL: %s", message)
            if _looks_like_auth_error(message):
                raise GrohmAuthError(message)
            # data + errors insieme = dati parziali validi: li teniamo.
            if data is None:
                raise GrohmError(message)
        return data or {}

    async def _gql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Come _post, ma con un nuovo login automatico se la sessione è scaduta."""
        if self.user is None:
            await self.login()
        try:
            return await self._post(query, variables)
        except GrohmAuthError:
            _LOGGER.debug("Sessione Grohm scaduta, nuovo login")
        await self.login()
        try:
            return await self._post(query, variables)
        except GrohmAuthError as err:
            # Il login è appena riuscito: non è un problema di credenziali
            # (es. permesso negato su una singola wallbox).
            raise GrohmError(str(err)) from err

    async def ensure_session(self) -> None:
        """`me` torna null (senza errori) quando il cookie non è più valido:
        in quel caso si rifà il login."""
        if self.user is None:
            await self.login()
            return
        try:
            data = await self._post(ME_QUERY)
        except GrohmAuthError:
            data = {}
        if not data.get("me"):
            await self.login()
            return
        user = GrohmUser.from_payload(data["me"])
        ensure_supported(user)  # l'account potrebbe essere diventato installatore
        self.user = user

    # ---------------------- autenticazione ----------------------

    async def login(self) -> GrohmUser:
        """Login con email/password. Rifiuta gli account non supportati
        (installatori) chiudendo subito la sessione appena aperta."""
        async with self._login_lock:
            self._session.cookie_jar.clear()
            data = await self._post(
                LOGIN_MUTATION,
                {"email": self._email, "password": self._password},
            )
            payload = data.get("login") or {}
            if payload.get("__typename") != "LoginSuccess":
                self.user = None
                raise GrohmAuthError(payload.get("message") or "Credenziali non valide")
            user = GrohmUser.from_payload(payload.get("user") or {})
            try:
                ensure_supported(user)
            except GrohmUnsupportedAccountError:
                self.user = None
                await self._safe_logout()
                raise
            self.user = user
            return user

    async def _safe_logout(self) -> None:
        try:
            await self._post(LOGOUT_MUTATION)
        except GrohmError:
            pass
        self._session.cookie_jar.clear()

    async def logout(self) -> None:
        """Chiude la sessione lato server (best effort)."""
        if self.user is not None:
            await self._safe_logout()
        self.user = None

    async def me(self) -> GrohmUser | None:
        data = await self._gql(ME_QUERY)
        me = data.get("me")
        return GrohmUser.from_payload(me) if me else None

    # ---------------------- wallbox ----------------------

    async def _paginate(self, query: str, root: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        for _ in range(_MAX_PAGES):
            data = await self._gql(query, {"page": page, "first": _PAGE_SIZE})
            node = data.get(root) or {}
            items.extend(node.get("items") or [])
            info = node.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                break
            page = int(info.get("nextPage") or page + 1)
        return items

    async def device_ids(self) -> list[str]:
        """Id di tutte le wallbox FISICHE dell'account, senza le reti.

        - privato: `myDevices`;
        - gestore: wallbox di tutte le reti + quelle non assegnate a nessuna rete.
        """
        await self.ensure_session()
        assert self.user is not None
        ids: list[str] = []
        if self.user.is_gestore:
            networks = await self._paginate(MY_NETWORKS_DEVICES_QUERY, "myNetworks")
            for network in networks:
                ids.extend(str(d["id"]) for d in network.get("devices") or [])
            orphans = await self._paginate(DEVICES_OUT_OF_NET_QUERY, "devicesOutOfNet")
            ids.extend(str(d["id"]) for d in orphans)
        else:
            devices = await self._paginate(MY_DEVICES_QUERY, "myDevices")
            ids.extend(str(d["id"]) for d in devices)
        return list(dict.fromkeys(ids))  # senza duplicati, ordine stabile

    async def devices(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """Stato completo di più wallbox in una sola richiesta."""
        if not ids:
            return {}
        query = build_devices_query(len(ids))
        variables = {f"id{i}": device_id for i, device_id in enumerate(ids)}
        data = await self._gql(query, variables)
        if not any(data.get(f"d{i}") for i in range(len(ids))):
            # Nessuna wallbox leggibile: spesso è la sessione scaduta in
            # silenzio. Verifico e, se serve, riprovo dopo il login.
            await self.ensure_session()
            data = await self._gql(query, variables)
        result: dict[str, dict[str, Any]] = {}
        for i, device_id in enumerate(ids):
            device = data.get(f"d{i}")
            if device:
                result[device_id] = device
        return result

    async def change_status(self, device_id: str, status: str) -> None:
        """status ∈ {PAUSED, RUNNING, RESUMED}."""
        await self._gql(
            CHANGE_STATUS_MUTATION, {"deviceId": device_id, "status": status}
        )

    async def edit_device(self, device_id: str, **fields: Any) -> None:
        """Campi ammessi: name, hourCost, locked, forceCharge."""
        data = await self._gql(EDIT_DEVICE_MUTATION, {"id": device_id, "input": fields})
        payload = data.get("editDevice") or {}
        if payload.get("__typename") == "EditDeviceError":
            raise GrohmError(payload.get("message") or "Modifica non riuscita")

    async def set_locked(self, device_id: str, locked: bool) -> None:
        await self.edit_device(device_id, locked=locked)

    async def force_charge(self, device_id: str) -> None:
        """Solo gestore. Resta attivo per il timer di 300 s della wallbox."""
        await self.edit_device(device_id, forceCharge=True)

    async def notify_viewing(self, device_id: str) -> None:
        """Chiede alla wallbox di pubblicare lo stato più spesso (best effort)."""
        await self._gql(NOTIFY_VIEWING_MUTATION, {"id": device_id})


def _looks_like_auth_error(message: str) -> bool:
    """Senza sessione il backend risponde HTTP 200 con l'errore GraphQL
    "User is not authenticated" (verificato su api.grohm.it); `me` invece torna
    semplicemente null."""
    text = message.lower()
    return any(
        word in text
        for word in (
            "not authenticated",
            "unauthenticated",
            "not logged",
            "authentication",
            "permission denied",
            "login required",
            "non autenticato",
        )
    )
