# Lab 6 - CLI vs NETCONF vs RESTCONF

## Objective

Compare three different methods for interacting with a Cisco IOS XE device:

- Traditional CLI
- NETCONF/YANG
- RESTCONF/YANG

The same logical operation is represented using each method so the differences between imperative CLI automation and model-driven APIs can be observed.

> The management interface `GigabitEthernet3` is protected and must never be modified by these examples.

---

## Lab Resource

The disposable resource used for write operations is:

```text
Interface: Loopback10
Initial IP: 10.255.10.1/32
Description: LAB6-API-COMPARISON
```

`Loopback10` is intended only for controlled API testing and must be removed after the lab.

---

# 1. Read Operation

## CLI

Show all interfaces:

```cisco
show ip interface brief
```

Show only Loopback10:

```cisco
show running-config interface Loopback10
```

### Characteristics

- Human-readable output.
- Designed primarily for interactive CLI use.
- Automation normally requires parsing text.
- Tools such as Ansible, Netmiko, Nornir or pyATS can consume the CLI.

---

## NETCONF

NETCONF uses structured XML and YANG models.

Transport:

```text
SSH
TCP/830
```

Example NETCONF filter:

```xml
<filter type="subtree">
  <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
    <interface>
      <Loopback>
        <name>10</name>
      </Loopback>
    </interface>
  </native>
</filter>
```

Typical NETCONF operation:

```text
<get-config>
```

Source datastore:

```text
running
```

### Characteristics

- Structured XML.
- Uses YANG models.
- Supports configuration datastores.
- Supports operations such as:
  - `<get>`
  - `<get-config>`
  - `<edit-config>`
  - `<commit>` when supported
- Better suited for model-driven automation than parsing CLI output.

---

## RESTCONF

RESTCONF exposes YANG data using HTTP methods.

Transport:

```text
HTTPS
TCP/443
```

Request:

```http
GET /restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=10
```

Header:

```http
Accept: application/yang-data+json
```

Example URL:

```text
https://172.30.30.41/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=10
```

### Characteristics

- Uses HTTP/HTTPS.
- Uses REST-style operations.
- Usually works with JSON or XML.
- Easy to test with:
  - Postman
  - curl
  - Python requests
  - automation platforms

---

# 2. Create Loopback10

## CLI

```cisco
configure terminal
interface Loopback10
 description LAB6-API-COMPARISON
 ip address 10.255.10.1 255.255.255.255
 no shutdown
end
```

This is an imperative approach.

The operator specifies the sequence of commands required to reach the desired state.

---

## NETCONF

NETCONF uses `<edit-config>`.

Target datastore:

```text
running
```

Example payload:

```xml
<config>
  <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
    <interface>
      <Loopback>
        <name>10</name>
        <description>LAB6-API-COMPARISON</description>
        <ip>
          <address>
            <primary>
              <address>10.255.10.1</address>
              <mask>255.255.255.255</mask>
            </primary>
          </address>
        </ip>
      </Loopback>
    </interface>
  </native>
</config>
```

Conceptual Python operation using `ncclient`:

```python
manager.edit_config(
    target="running",
    config=payload,
)
```

NETCONF sends structured configuration instead of CLI commands.

---

## RESTCONF

RESTCONF can create the resource using HTTP `POST`.

Request:

```http
POST /restconf/data/Cisco-IOS-XE-native:native/interface
```

Headers:

```http
Accept: application/yang-data+json
Content-Type: application/yang-data+json
```

Body:

```json
{
  "Cisco-IOS-XE-native:Loopback": [
    {
      "name": 10,
      "description": "LAB6-API-COMPARISON",
      "ip": {
        "address": {
          "primary": {
            "address": "10.255.10.1",
            "mask": "255.255.255.255"
          }
        }
      }
    }
  ]
}
```

Possible successful HTTP responses include:

```text
200 OK
201 Created
204 No Content
```

The exact response depends on the IOS XE implementation.

---

# 3. Modify Loopback10

## CLI

```cisco
configure terminal
interface Loopback10
 description LAB6-CLI-UPDATED
end
```

The CLI changes the required command directly.

---

## NETCONF

NETCONF modifies the structured configuration using another `<edit-config>` operation.

Example:

```xml
<config>
  <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
    <interface>
      <Loopback>
        <name>10</name>
        <description>LAB6-NETCONF-UPDATED</description>
      </Loopback>
    </interface>
  </native>
</config>
```

---

## RESTCONF PATCH

RESTCONF can modify only part of the resource using `PATCH`.

Request:

```http
PATCH /restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=10
```

Body:

```json
{
  "Cisco-IOS-XE-native:Loopback": [
    {
      "name": 10,
      "description": "LAB6-RESTCONF-PATCH"
    }
  ]
}
```

`PATCH` is useful when only part of the existing resource needs to change.

---

# 4. Replace Loopback10 with RESTCONF PUT

Request:

```http
PUT /restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=10
```

Example body:

```json
{
  "Cisco-IOS-XE-native:Loopback": [
    {
      "name": 10,
      "description": "LAB6-RESTCONF-PUT",
      "ip": {
        "address": {
          "primary": {
            "address": "10.255.10.10",
            "mask": "255.255.255.255"
          }
        }
      }
    }
  ]
}
```

Conceptually:

```text
PATCH = modify part of a resource
PUT   = send the desired representation of the resource
```

Actual behavior must always be validated against the YANG model and IOS XE implementation.

---

# 5. Delete Loopback10

## CLI

```cisco
configure terminal
no interface Loopback10
end
```

---

## NETCONF

NETCONF can remove the resource using an operation attribute.

Conceptual example:

```xml
<config>
  <native
    xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native"
    xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
    <interface>
      <Loopback nc:operation="delete">
        <name>10</name>
      </Loopback>
    </interface>
  </native>
</config>
```

---

## RESTCONF

Request:

```http
DELETE /restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=10
```

Typical successful response:

```text
204 No Content
```

A subsequent `GET` should normally return:

```text
404 Not Found
```

confirming that the resource no longer exists.

---

# Comparison

| Feature | CLI | NETCONF | RESTCONF |
|---|---|---|---|
| Transport | SSH | SSH | HTTPS |
| Default Port | 22 | 830 | 443 |
| Data Format | Text | XML | JSON/XML |
| Data Model | CLI syntax | YANG | YANG |
| Read | show commands | get / get-config | GET |
| Create | config commands | edit-config | POST / PUT |
| Partial Update | config commands | edit-config | PATCH |
| Replace | config commands | edit-config | PUT |
| Delete | no command | edit-config delete | DELETE |
| Human interaction | Excellent | Low | Good |
| Machine automation | Requires parsing | Excellent | Excellent |
| Postman support | No | No | Yes |
| Python support | Netmiko/NAPALM | ncclient | requests |

---

# Lab 6 Usage

Lab 6 uses all three approaches for different purposes:

```text
CLI
 |
 +-- Ansible
 +-- Nornir
 +-- pyATS / Genie

NETCONF
 |
 +-- ncclient
 +-- Cisco-IOS-XE-native YANG

RESTCONF
 |
 +-- Python requests
 +-- Postman
 +-- Cisco-IOS-XE-native YANG
```

The objective is not to replace the CLI completely.

The objective is to understand when traditional CLI automation is appropriate and when model-driven APIs such as NETCONF and RESTCONF provide better structured interfaces for network automation.

---

# Safety

The following Lab 6 management interface must never be modified by these API examples:

```text
GigabitEthernet3
```

All write tests must use:

```text
Loopback10
```

After testing, Loopback10 must be removed so the routers return to the intended Lab 6 topology.
