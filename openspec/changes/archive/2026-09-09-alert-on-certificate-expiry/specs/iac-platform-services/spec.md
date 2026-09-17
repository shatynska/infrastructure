## ADDED Requirements

### Requirement: An Expiring TLS Certificate Is Alerted On Before It Expires
The platform stack SHALL alert when a TLS certificate the shared reverse proxy serves is approaching expiry, with enough lead time remaining to reissue it before any client is affected. The notification a recipient actually receives SHALL identify which certificate is affected, including when more than one is approaching expiry at the same time.

The threshold SHALL be strictly less than the lead time at which the reverse proxy begins renewing a certificate on its own, so that the alert reports a renewal that did not happen rather than one that has not happened yet.

This requirement is satisfied by metrics the reverse proxy already publishes about the certificates it holds. It does not require probing a public hostname and is not a check made from outside the host, so it does not cover a failure that is invisible from the host itself.

#### Scenario: A certificate approaching expiry raises an alert
- **WHEN** a certificate the shared reverse proxy serves is within the configured number of days of its expiry timestamp, for a sustained period
- **THEN** an alert SHALL fire identifying that certificate by the hostname it was issued for

#### Scenario: Several certificates approaching expiry are each identified
- **WHEN** more than one certificate is within the configured number of days of expiry at the same time
- **THEN** each affected hostname SHALL be named in a notification that is delivered, rather than the group collapsing into a single notification that names none

#### Scenario: A certificate renewing normally raises no alert
- **WHEN** the shared reverse proxy renews a certificate on its own schedule and the replacement's expiry moves further out
- **THEN** no alert SHALL fire, because the threshold leaves normal renewal strictly more lead time than the alert requires

#### Scenario: A superseded certificate does not raise an alert against a healthy hostname
- **WHEN** a certificate is renewed and a record of the superseded certificate's earlier expiry remains observable
- **THEN** no alert SHALL fire for that hostname on account of the superseded record, because the hostname's certificate is not in fact approaching expiry

#### Scenario: Certificate expiry no longer being observed raises an alert
- **WHEN** certificate expiry stops being observable at all — whether because the source publishing it has become unreachable, or because it remains reachable but no longer publishes that measurement
- **THEN** an alert SHALL fire reporting that condition, rather than the certificate alert silently evaluating an empty result and never firing again
