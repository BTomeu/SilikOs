# `silik ask`: l'assistent que ensenya les ordres i no n'executa cap

**Resum (català).** `silik ask PREGUNTA` respon una pregunta sobre *aquest* sistema amb les ordres exactes, i no
n'executa cap. Té dues capes:

- **Fora de línia (la de sempre, sense xarxa ni model).** Cerca en el que el sistema sap de si mateix: totes les
  ordres de `silik` amb la seva ajuda (també les dels plugins), les adreces del COMMAND bar, els manuals que
  instal·la el paquet, els dispositius USB que SilikOS coneix, les files de `silik doctor` d'ara mateix (només de
  l'àrea de què va la pregunta) i, al final, els noms de les pàgines `man`. Dona fins a cinc respostes; cadascuna és
  una línia d'ordres per copiar, una línia que diu què fa i les paraules de la pregunta que hi coincideixen.
- **Amb un model de llenguatge (`--model`), només si tu ho demanes.** Fa servir la Messages API d'Anthropic amb la
  **teva** clau. Abans d'enviar res ensenya exactament què envia (la pregunta, les respostes fora de línia i les
  files de `silik status` i `silik doctor` de què va la pregunta, amb l'equip, l'usuari, els camins de casa, les
  adreces i els números de sèrie canviats per marcadors). El primer cop demana permís en un terminal. El que torna és
  text; les ordres que proposa es comproven i es marquen, i no se n'executa cap.

Per apagar-ho: no cal fer res (sense `--model` no surt res de la màquina); `silik ask consent off` retira el permís,
`silik ask key rm` esborra la clau, i `model = off` a `/etc/silikos/ask.conf` treu la capa del model per a tothom.
**No s'ha provat mai contra l'API real** (aquí no hi ha clau): s'ha provat contra un servidor de prova que comprova la
forma de la petició.

---

## What it is for

A workstation's assistant, the SilikOS way: every action shows the command it runs, nothing leaves the machine
unasked, and nothing is said to be ok that was not seen. So the assistant does not act. It answers with command
lines, says where each comes from, and the person runs what they choose.

```
silik ask why is my CAN adapter not working       the offline layer: up to five commands, each with its reason
silik ask --json QUESTION...                      the same for a program
silik ask --verbose QUESTION...                   also the read-only commands it ran (the doctor's)
silik ask --limit 10 QUESTION...                  more answers (1 to 20)
silik ask -- what does --dry-run do               a question with a word that starts with - goes after --
silik ask --model QUESTION...                     the same, then a language model's answer (opt-in, below)
silik ask --show-context QUESTION...              exactly the bytes --model would send; sends nothing
silik ask key set                                 your API key, typed without echo (or piped in), kept in a 0600 file
silik ask consent                                 is consent stored, and for which address
silik ask config                                  the model, the address, where the key comes from
```

It runs no command for you in either layer. What it runs itself is read-only: the probes of `silik doctor` for the
areas the question names, `silik status`, and `apropos` as a last tier; `--verbose` lists them.

## The offline layer

No network, no model, no index kept on disk: each run reads what is on the system at that moment, so an answer can
not name a command that was removed, and a plugin's commands are answered as soon as its file is there.

| What is searched | Where it comes from | What an answer looks like |
|---|---|---|
| Every command of `silik`, plugins included | its argparse tree, walked at run time: each command, each option that has a help line, each choice (`silik look island`) | `silik dev can` and its help |
| The COMMAND bar's addresses | `silik-command`'s own table, in English, Catalan and Spanish | the address's command line, with its title in the question's language |
| The handbooks | the Markdown files the package installs in `/usr/share/doc/silik-tools` (from a checkout: `packages/silik-tools/files/doc`) | each command line they name, with the line that says what it does; and each section as `less -p HEADING FILE` |
| The tools SilikOS knows by name | `silik dev tools` and `silik eda tools`' tables | the tool when it is installed, `sudo dnf -y install PACKAGE` when it is not |
| The USB devices SilikOS knows | `hardware.tsv` (adapters, probes, logic analysers) | the command the table gives for the device, with its driver and whether it was tried with a real device |
| The doctor's rows of right now | `silik doctor`'s probes, only for the areas the question is about (CAN, USB, serial: bench; firewall, disk encryption: security; ...) | the row's own fix command, or `silik doctor AREA`, with the row |
| man page names | `apropos -l -s 1,5,8`, only when fewer answers than asked were found | `man 8 ip` |

A command of `silik` found in a handbook is answered only if this system's `silik` takes it; another program found
there only if it is installed.

**Ranking**, plain and explainable (the constants are at the top of the ranking section of `plugins/ask.py`):

1. The question is cut into words: lower case, no accents, the plural *s* off; `st-link` also as `stlink`, `can0`
   also as `can`. The stop words of English, Catalan and Spanish go.
2. A word counts 3 when it is in the entry's command line, 2 in the line that says what it does, 1 in the text
   around it, and is weighted by how rare it is among the entries (`log(1 + entries / entries that have it)`).
3. Another word for the same thing counts 0.8 of that: a small table of the engineering words in the three languages
   (`flash` / `program` / `gravar` / `programar`, `tallafoc` / `cortafuegos` / `firewall`, `adaptador` / `lector` /
   `adapter` / `interface`, ...). The answer says so: `matched: tallafoc (as firewall)`.
4. The sum is scaled by how many of the question's words the entry has, and by the kind of entry: a command of
   `silik` 1.25, a handbook's section 0.7, a man page 0.5. When the question says that something does not work
   ("why", "not working", "no funciona", "falla"), a doctor's row that is not ok counts 2.2 times.
5. At most two answers may be forms of one command (`silik dev can ...`); an answer weaker than 0.3 of the first is
   left out; ties go by kind, then by the command line. The same question over the same system gives the same list.

`CAN` in capitals is the bus. `can` in lower case is the bus too, except where English makes it the verb ("how can
I", "can you"): this is the one word with a rule of its own.

**Time.** Measured on 13/11/2026 in an `almalinux:9` container (AlmaLinux 9.8, Python 3.9.25) with the package built
and installed there, so that `silik` and the plugin run compiled as on an installed system; on the build machine (4
cores, shared with other jobs at that moment); 20 runs of the whole command each, wall time:

| Question | The doctor's areas read | min | median | max |
|---|---|---|---|---|
| `silik ask compiler cache` | none | 0.110 s | 0.123 s | 0.180 s |
| `silik ask why is my CAN adapter not working` | bench | 0.116 s | 0.123 s | 0.185 s |
| `silik ask com actualitzo el sistema` | system | 0.132 s | 0.144 s | 0.195 s |
| `silik ask bloquea la pantalla` | security, graphics | 0.181 s | 0.212 s | 0.292 s |

For scale, there and then: `silik --version` 0.039 s, `silik status` 0.042 s, `python3 -c pass` 0.010 s (medians).
The search itself (about 400 entries read, cut into words and ranked) is 0.05 to 0.07 s of each; the rest is Python
starting, `silik` loading and the doctor's probes. Not measured on an installed SilikOS, where the doctor has real
devices and services to read (`silik doctor` whole is 0.14 to 0.27 s on a clean EL 9, `docs/CONCEPT.md`).

## The COMMAND bar

`plugins/ask.cmd.json` gives the plain addresses: `ask/key`, `ask/consent`, `ask/consent-off`, `ask/config`.

A question needs typing, which the bar's addresses cannot take, so the bar itself needs a change. It is written as
`docs/patches/ask-command-bar.patch` (applied by the main session at the merge; `tests/test_ask.py` applies it to a
copy):

- A line that starts with `?` is a question. While it is typed the list has one entry, whose foot shows
  `$ silik ask QUESTION`. Enter asks the offline layer and lists the answers (`?1` ... `?5`, each with its command and
  what it does).
- Enter on an answer **puts its command in the bar as `$ COMMAND` and runs nothing**; the foot says "Enter to the
  bar". The person reads it, changes it (an interface's name, a file), and Enter again runs it in a terminal that
  stays open.
- For that, a line that starts with `$` is a command line, run with `sh -c` in a terminal. This is new for the bar and
  is the owner's to accept: without it an answer that is not an address could only be read.

The model layer is not in the bar: it asks a question at a terminal.

## The model layer (`--model`)

Off until asked for, each time, by the switch. It uses [Anthropic's Messages API](https://platform.claude.com/docs/en/api/messages)
with the user's own API key: SilikOS has no account, no server and no key of its own, and sees nothing of what is
asked.

### Exactly what is sent, and to whom

One HTTPS request, `POST {base_url}/v1/messages`, where `base_url` is `https://api.anthropic.com` unless a setting
says otherwise (below). Nothing else is contacted. Its headers: `content-type: application/json`,
`anthropic-version: 2026-10-21`, `x-api-key: <your key>`, `user-agent: silik-ask/<silik's version>` and, with the
fallback on, `anthropic-beta: server-side-fallback-2026-07-01`. Its body:

| Field | Value |
|---|---|
| `model` | `claude-opus-5-5` unless `model = ...` is set |
| `max_tokens` | 16000 (the most the answer and the model's thinking may use; `max_tokens = ...`) |
| `output_config.effort` | `medium` (`effort = low` ... `max`) |
| `system` | The instructions for the model: what SilikOS is, that nothing it writes is run, to give exact command lines in code blocks, to treat the data as data and never as instructions, to keep the placeholders, to answer in the question's language; and **the list of `silik`'s commands, generated from this system's own `silik` at that moment** |
| `messages` | One message, made of three parts: the question; the offline layer's answers (command and what it does); and a JSON block with `silik status --json` and the rows of `silik doctor` of the areas the question is about that are not ok or share a word with the question (at most 24) |
| `fallbacks` | `"default"` on the models the API documents it for (below); absent with `fallback = off` |

That is all of it. No file of the home folder, no environment variable, no shell history, no list of processes or
packages, no hardware inventory beyond what `silik status` prints (the graphics cards' names, the kernel's version).
`silik ask --show-context QUESTION` prints the body byte for byte and sends nothing; `--dry-run` shows the message and
stops. Every `--model` run prints the message before it is sent, and the request itself as a `$ curl ...` line with
the key as `$ANTHROPIC_API_KEY`.

**Redaction.** Before any of it is put together, these are replaced, in the question too:

| What | Becomes |
|---|---|
| The host name (short and full), its domain | `<host>`, `<domain>` |
| The user's login name, real name, and the home folder | `<user>`, `<name>`, `<home>`; other people's `/home/NAME` as `/home/<user-N>`; `/run/user/UID` as `/run/user/<uid>` |
| IPv4 and IPv6 addresses (with a zone, in a URL, mapped) | `<ip-N>`; loopback (`127.0.0.0/8`, `::1`) and the unspecified address stay: they are the same on every machine |
| MAC addresses (`aa:bb:..`, `aa-bb-..`, `aabb.ccdd.eeff`) | `<mac-N>` |
| Serial numbers by their label (`Serial Number:`, `S/N`, `iSerial`, `ID_SERIAL=`, `machine-id`), the `/dev/serial/by-id` and `/dev/disk/by-*` names, `usb-...-ifNN` names, UUIDs, hexadecimal numbers of 16 digits or more | `<serial-N>`, `<id-N>`, `<uuid-N>` |
| The names of the EDA boxes and of the Wine prefixes (they are often a project's name) | `<box-N>`, `<prefix-N>` (`default` stays) |
| E-mail addresses | `<email-N>` |
| An API key (`sk-...`), a `user:password@` in a URL, a value after `password` / `token` / `secret` / `api key` | `<key>`, `<credentials>`, `<secret>`: these are never put back |

A name of five letters or more is replaced inside longer words too. A name that is a word of `silik`'s own commands
(a host called `vm`, a user called `dev`) or `localhost` / `root` is not a name and is left: replacing it would
rewrite the commands. The placeholders in the model's answer are put back on this machine, so that a proposed
command can be copied; the real values never left.

**What redaction does not do.** It knows patterns and this machine's own names. A project's name, a customer's name
or a part number typed in the question, or a device's product string, is sent as it is: read the message that is
shown before saying yes. Text that came from a device (a USB product name) is in the data block, one line each and
without control characters, as JSON strings; the model is told it is data, and whatever it answers is never run.

### Consent, the key, the settings

- **Consent.** The first `--model` shows what it would send and asks, at a terminal: "Send this to ADDRESS, now and
  from now on without asking again?". Yes is remembered in `~/.config/silikos/ask.conf` (`consent = ADDRESS`) for
  that address only: another `base_url` is asked again. Without a stored consent and without a terminal (a script, a
  pipe, `--json`) it refuses. `silik ask consent off` withdraws it; `silik ask consent on` asks the same question;
  `/etc/silikos/ask.conf` cannot give a person's consent.
- **The key.** From the variable `ANTHROPIC_API_KEY`, else from `~/.config/silikos/ask.key`. `silik ask key set`
  reads it from the terminal without echo (or from a pipe: `pass show anthropic | silik ask key set`), never from the
  command line, and writes the file with mode 0600 in a 0700 folder. A key file that others can read, that is a link,
  or that is not the user's, is refused with the reason. The key is never printed and never written to a log; it is
  sent in one header, to the address shown, and a redirect to another address is not followed.
- **The settings**, `key = value` lines in `/etc/silikos/ask.conf` (the system's) and `~/.config/silikos/ask.conf`
  (the person's, which wins):

| Key | Default | |
|---|---|---|
| `model` | `claude-opus-5-5` | a model id of the API. In `/etc/silikos/ask.conf` only: `model = off` turns the model layer off for everybody on the system |
| `base_url` | `https://api.anthropic.com` (or `$ANTHROPIC_BASE_URL` when no file names one) | a company's own gateway that speaks the Messages API. `https://` only (`http://` for this machine itself) |
| `auth` | `x-api-key` | `bearer`: the key as `Authorization: Bearer`, for a gateway that wants it so |
| `effort` | `medium` | `low` `medium` `high` `xhigh` `max` |
| `max_tokens` | `16000` | 256 to 128000 |
| `timeout` | `120` | seconds, 5 to 3600 |
| `fallback` | `auto` | `off`: no `fallbacks` field and no beta header |

These values are the ones the API's reference gives (read on 13/11/2026 from the `claude-api` reference of the build
tool, dated 03/11/2026: the request's headers and body, API version `2026-10-21`, `claude-opus-5-5` as the default
model, `effort` as the control of how much it thinks with `medium` as that model's starting point, 16000 as the
`max_tokens` of a request that is not streamed, no sampling parameters). [A] `medium` and 16000 are the reference's
starting points, not measured here.

**The fallback: the owner's decision.** The reference says a request to `claude-opus-5-5` (and to
`claude-fable-5-2`, `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5-5`) may be declined by a safety classifier
even when it is harmless (it names security tooling as an example), and tells applications to send
`fallbacks: "default"` with the beta header `server-side-fallback-2026-07-01`, so that the API answers with another
model inside the same request instead of returning nothing. `silik ask` sends it by default, shows it (the field is
in `--show-context`, the header in the `$ curl` line), and says after the answer when another model answered and what
each attempt used. It is the one place where one question can be billed as more than one attempt, which is why it
has a switch: `fallback = off`.

### What comes back

Text, shown as text after `answer of MODEL (a model's text: read it as advice; nothing was run)`, with control
characters, terminal escape sequences and the characters that reorder or hide text removed. Then the command lines
of the answer (every line of its code blocks, and `silik ...` in backticks), each marked:

- `[checked: silik has it]`: a `silik` command that this system's parser takes. It says the command exists and is
  well formed, not that it is harmless: `silik win rm NAME` is one too. A `silik` command that runs a program handed
  to it (`silik eda run NAME -- ...`, `silik win run`, arguments after `silik win open FILE`) is not checked.
- `[checked: read-only]`: one of a short list of commands that only read (`ip ... show`, `lsusb`, `journalctl` with
  reading switches, `systemctl status`, `rpm -q`, `dnf list`, `candump IFACE`, `cat` of `/proc` and `/sys`, ...) with
  words the list allows: `ip link show` is, `ip link set` is not.
- `[not checked]`: everything else, and any line with something of the shell in it (`;`, `|`, `>`, `$`, quotes,
  backticks...). `rm -rf ~` is this, and so is `silik status; rm -rf ~`.

None is run. After the answer: `tokens: N in, M out`, as the API reports them.

One request per question. No retry on any error: a 401, 429 (with the wait the API names), 5xx, a timeout or no
connection is said in a line, with the API's own words, and the command ends (exit 3; a refusal by the model: 4).

## What it costs

The offline layer: nothing. The model layer: the user's own Anthropic API account is billed by Anthropic for the
tokens of each request, at the price of the model in use; SilikOS adds nothing and receives nothing. One question is
one request. The request for the CAN question, in the container above, was 9757 bytes (the instructions with the
list of commands 8126 characters, the message 1159): how many tokens that is, and how many an answer adds, is what
the API reports, and was not seen. The price per token is Anthropic's and changes: it is not stated here; the usage line
after each answer is the number to multiply.

## How to turn it off

- Do nothing: without `--model` nothing is sent, and there is no background service, no telemetry and no update check
  in `silik ask`.
- `silik ask consent off`: `--model` sends nothing until yes is said again at a terminal.
- `silik ask key rm`, and unset `ANTHROPIC_API_KEY`: no key, no request.
- For every user of a machine: `model = off` in `/etc/silikos/ask.conf`.
- A company that wants the traffic through its own gateway: `base_url = https://gateway...` there.

## Not verified

- **Not run against the real API.** No key here, and the build machine may not reach `api.anthropic.com`. The
  request was run against a local stand-in server (`tests/test_ask.py`, class `Fake`) that refuses what the
  reference does not document: the path, the three headers, the body's fields and their types, no sampling
  parameters, no thinking budget, no prefill, `fallbacks` only with its beta header. So: the shape is checked against
  the reference as read; whether the real API takes it, what the model answers, how good the answers are, how long
  they take and what they cost are not known. The first person with a key should run
  `silik ask --model why is my CAN adapter not working` and say.
- The instructions for the model were written, not tried on a model.
- [A] A gateway (`base_url`, `auth = bearer`): no real one was tried.
- The offline answers on an installed SilikOS with real devices: the doctor's rows here were made up for the tests
  (a CAN interface that is down) or were those of a container (nothing plugged in).
- `apropos` as the last tier was run in `almalinux:9` with `man-db` and the few man pages that container has (asked
  for a program of man-db that nothing else on the system names, it answers with that program's man page); not with the man
  pages of a full installation.
- The COMMAND bar's `?` and `$`: the logic is tested on a patched copy; the window (GTK) with them was not opened.
- The ranking is a word search: it finds what is worded like the question. Its constants were set by reading the
  answers to about thirty questions in the three languages on this repository; no larger set was scored.
