"""Read-only Kasa adapter; no control methods are invoked here."""

import asyncio
import time

from butler.services import smart_plugs
from .models import Device, Reading


class ReadFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class KasaReader:
    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout

    def read(self, device: Device) -> Reading:
        return asyncio.run(self._read(device))

    async def _read(self, definition: Device) -> Reading:
        device = None
        try:
            try:
                kasa = smart_plugs._kasa()
            except RuntimeError as exc:
                raise ReadFailure('dependency_missing') from exc
            async with asyncio.timeout(self.timeout):
                # Existing switches intermittently reject a KLAP handshake.
                # Retry only that read failure, inside the same overall deadline.
                for attempt in range(3):
                    try:
                        device = await kasa.Discover.discover_single(
                            definition.host, credentials=smart_plugs._credentials(), timeout=self.timeout)
                        if device is None:
                            raise ReadFailure("read_failed")
                        await device.update()
                        if type(device.is_on) is not bool:
                            raise ReadFailure("invalid_reading")
                        return Reading(device.is_on, time.time())
                    except kasa.exceptions.AuthenticationError:
                        if device is not None:
                            await asyncio.wait_for(device.disconnect(), timeout=1)
                            device = None
                        if attempt == 2:
                            raise ReadFailure('authentication_failed')
                        await asyncio.sleep(0.1)
        except TimeoutError as exc:
            raise ReadFailure("timeout") from exc
        except ReadFailure:
            raise
        except Exception as exc:
            # Never expose library exception strings (they can include credentials).
            raise ReadFailure("read_failed") from exc
        finally:
            if device is not None:
                try:
                    await asyncio.wait_for(device.disconnect(), timeout=1.0)
                except Exception:
                    pass
