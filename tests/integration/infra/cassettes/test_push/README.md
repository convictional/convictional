# Hand-rolled Expo Push cassettes

These cassettes were written from Expo's documented response shape rather
than recorded against `https://exp.host/--/api/v2/push/send`. Simulator
builds can't produce a real `ExponentPushToken` (no `aps-environment`
entitlement), so a TestFlight (or any physical-device) build is required to
record real exchanges.

When a physical-device build is available, re-record:

```
ENV=test pytest tests/integration/infra/test_push.py::test_apns_* --record-mode=rewrite
```

Tests that can't be cassetted (transport-layer failures, request-shape
inspection, parametrized error matrices) remain patch-based in `test_push.py`.
