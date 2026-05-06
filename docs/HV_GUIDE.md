# HyperVisor (HV) Cracks Guide

SteaMidra can download and apply HyperVisor bypasses for Denuvo-protected games via the **HV Auto** button on the Home tab. This guide explains what HV cracks are, the security trade-offs, and exactly how to use them.

> This guide draws from Csrin's article at cs.rin.ru:
> https://cs.rin.ru/forum/viewtopic.php?f=10&t=156407
> Read it at least once — it covers the security topics in greater depth.

---

## Video Tutorials

Two community tutorials covering HV setup and usage:

- **Tutorial 1:** https://www.youtube.com/watch?v=J9fVenXstAc
- **Tutorial 2:** https://www.youtube.com/watch?v=lyjVuDDEJfo

---

## What Is a HyperVisor Crack?

Denuvo relies on integrity checks, timing analysis, and detection of debugging or emulation environments. A HyperVisor-based bypass places a custom kernel driver below Windows at the CPU level, intercepting those checks transparently — without modifying the game binary at all.

A standard hypervisor (VirtualBox, VMware, Hyper-V) runs as an application on top of your OS. A **bare-metal hypervisor** runs directly on the hardware, so even your OS accesses hardware resources through it. This puts the bypass driver outside Denuvo's visibility entirely.

Every HV crack ships as two parts:

1. **VBS.cmd** — a command-line script that checks your current security settings and adjusts them so the system can load the HV driver. It includes a Revert Changes option. Current version: **v1.6.2**. Universal across all HV games.
2. **The crack itself** — game-specific EXEs/DLLs that do the actual Denuvo bypass, plus additional files such as a Goldberg Steam emulator to pass Steam's underlying protection. These files work only for the specific game version they were built for.

---

## Windows Virtualization-Based Security (VBS)

Modern Windows 10 and 11 systems use a bare-metal hypervisor (the Windows hypervisor) to run security components in isolated virtual spaces, safe from even a fully compromised OS. This umbrella is called Virtualization-Based Security (VBS).

The components it protects:

- **Memory Integrity (HVCI)** — detects unexpected modifications to Windows kernel code and restricts suspicious kernel memory allocations.
- **Credential Guard** — stores passwords, authentication data, and biometric data in an isolated environment.
- **Windows Hello / Enhanced Sign-in Security** — stores login data (PIN, facial recognition, fingerprint) using VBS. Login methods tend to break when VBS components are disabled.
- **System Guard (Secure Launch)** — protects the OS boot process and System Management Mode (SMM) from rootkits. Backed by TPM 2.0, it continuously verifies system integrity after boot.
- **HyperGuard** — uses VBS to protect PatchGuard (Windows kernel anti-tampering) from rootkits.
- **Guarded Host** — datacenter feature; rarely present in home environments.

The Windows hypervisor cannot be disabled directly. Each feature above signals that VBS needs to be active, which loads the hypervisor. To stop the hypervisor from loading, you must disable all of those features and add a boot option that prevents Hyper-V from loading it.

---

## Why You Can't Use Both at Once

Nested virtualization (stacking two hypervisors) is technically possible, but Microsoft only supports it for other Windows hypervisors running inside Hyper-V VMs — not for third-party bare-metal hypervisors. The Windows hypervisor does not pass hardware-assisted virtualization features (Intel VT-x / AMD-V) down to the OS. The HV crack driver needs direct access to those CPU features, so it cannot coexist with the Windows hypervisor.

Other virtualization tools hit the same wall. VMware users have to disable VBS features or be forced onto the Windows hypervisor. VirtualBox falls back to software emulation and runs extremely slowly as a result.

You have no choice but to disable all VBS features and the Windows hypervisor before using an HV crack.

---

## Driver Signature Enforcement (DSE)

Recent Windows versions refuse to load kernel drivers not approved and signed by Microsoft (WHQL). The HV crack driver is unsigned by nature — no piracy-adjacent driver will ever receive a Microsoft certificate. You must disable DSE for one boot cycle to load it.

VBS.cmd handles this using the advanced boot menu option (press F7 or 7 at Startup Settings during reboot). This is the safest method — it only disables DSE for that single boot and reverts automatically on the next reboot.

---

## Security Implications

Disabling these features has real consequences. Csrin's assessment (10 years in security-focused system administration):

**The argument for accepting the risk:**
Common threats — info stealers from fake download buttons, ransomware, DDoS botnets — usually do not need kernel-level access to do their damage. A good ad blocker, trusted sources, and user awareness stop most of them. Virtualization features can also reduce system performance, which matters in gaming.

**The argument against:**
You give up protections that evolved from decades of security research. If you encounter more advanced malware with DSE and memory integrity disabled, it can compromise your system completely, join a botnet undetected, or spread to other devices on your local network. Widespread use of HV cracks creates an attractive target for manipulated fake releases — people who run them can be expected to have disabled every protection including AV scanning. A serious vulnerability in the HV driver itself grants maximum, undetectable system access even if you compiled it from source.

Whether any specific game is worth those trade-offs is your decision alone.

---

## Step-by-Step: Using HV via SteaMidra

**Prerequisites:** The game is already installed. SteaMidra has applied the Lua/manifest fix.

1. Open SteaMidra and go to the **Home** tab.
2. Select your game from the dropdown.
3. Click **HV Auto** (under Fixes/Bypasses).
4. SteaMidra downloads and extracts the HV crack files into the game folder.
5. Follow the standalone steps below to actually run the game.

---

## Step-by-Step: Standalone Setup (Every Time You Play)

**Before launching the game:**

1. **Open Windows Security → Device Security → Core isolation.**
   Turn off **Memory Integrity** if it is on. Reboot if prompted.
2. Navigate to the game folder. Right-click **VBS.cmd** → Run as Administrator.
3. Press **1** to apply the security changes. VBS.cmd disables VBS, Credential Guard, and other components.
4. When prompted, reboot your PC.
5. At the **Startup Settings** screen (black screen after POST), press **F7** or **7** to disable Driver Signature Enforcement for this boot.
6. Windows loads. Launch the game normally.

**After you finish playing:**

7. Right-click **VBS.cmd** → Run as Administrator.
8. Press **3** → **Revert Changes**. This restores all security settings.
9. Reboot. Your system returns to its normal security state.

> **Do not skip the revert step.** Running with DSE disabled and HVCI off beyond your play session leaves your system exposed.

---

## Best Practices

- **Check your system first.** Run a reputable portable AV scanner before disabling security features. Have a look at Task Manager for unfamiliar processes.
- **Verify files.** Confirm that the crack files come from a trusted source. Check checksums if available from a separate trusted location.
- **Prefer open source.** If source code is included, compare it against the GitHub projects the HV driver is based on. Compile it yourself if you know how.
- **Use only approved VBS.cmd versions.** Do not use scripts from unknown sources. The one bundled by SteaMidra (v1.6.2) is open source and reviewed.
- **Revert after every session.** This is not optional. Leaving DSE off and HVCI disabled permanently removes meaningful kernel protection.
- **Kernel anti-cheats will not work** while DSE is off. FACEIT, Vanguard, and Easy Anti-Cheat require DSE. Do not try to use them in the same boot session.
- **BitLocker users:** Make sure you have your BitLocker recovery key before making changes. Disabling VBS components can trigger a recovery key prompt on next boot.
- **Windows Hello users:** Know your normal login password before disabling VBS. Windows Hello PIN/biometric login may break while these features are off.
- **Do not use on a work or school machine.**
- **Advanced option:** Run HV cracks inside a virtual machine with GPU passthrough (KVM on Linux, or Hyper-V with nested virtualization), or on a dedicated PC with no personal data. Performance penalty applies.

---

## Frequently Asked Questions

**Does SteaMidra download VBS.cmd?**
SteaMidra downloads the full HV crack package for your game, which includes VBS.cmd. You do not need to find it separately.

**Does this work on every Denuvo game?**
HV cracks are game-specific. SteaMidra only offers an HV download when a compatible release exists for your installed game version. If no release exists, the button will report no available bypass.

**Can I leave the security settings disabled permanently?**
You can, but you should not. Every session without HVCI and DSE is a session where kernel-level malware faces no meaningful resistance.

**The game asks for the crack to run with admin rights — is that normal?**
Some crack components need elevated permissions. However, closed-source binaries that require admin rights are a red flag. Prefer releases where the admin-required component is the VBS.cmd script only, and any closed-source binaries run without elevation.

---

## Related Resources

- Csrin's full article: https://cs.rin.ru/forum/viewtopic.php?f=10&t=156407
- Tutorial 1: https://www.youtube.com/watch?v=J9fVenXstAc
- Tutorial 2: https://www.youtube.com/watch?v=lyjVuDDEJfo
- SteaMidra Discord: https://discord.gg/V8aZqnbB84
