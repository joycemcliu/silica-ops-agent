<#
Human-only device-metadata repair. Never executed end-to-end in this session.
Inspect is read-only. Repair and Rollback require explicit action and confirmation.
Id must come from the read-only scan and native hang confirmation, never a saved example.
Rollback restores the empty property and can reintroduce the startup hang.
#>
#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Id,

    [ValidateSet('Inspect', 'Repair', 'Rollback')]
    [string]$Action = 'Inspect',

    [string]$BackupPath
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run this script on the affected Windows server.' }
if ($Action -ne 'Inspect' -and [string]::IsNullOrWhiteSpace($BackupPath)) {
    throw 'Repair and Rollback require -BackupPath.'
}

if (-not ('DeviceFriendlyName' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class DeviceFriendlyName {
    [StructLayout(LayoutKind.Sequential)]
    struct Info {
        public uint Size;
        public Guid ClassGuid;
        public uint DevInst;
        public UIntPtr Reserved;
    }
    [DllImport("setupapi.dll", SetLastError=true)]
    static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr cls, IntPtr hwnd);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern bool SetupDiOpenDeviceInfoW(IntPtr set, string id, IntPtr hwnd, uint flags, ref Info info);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern bool SetupDiGetDeviceRegistryPropertyW(IntPtr set, ref Info info, uint property,
        out uint type, [Out] byte[] buffer, uint size, out uint required);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    static extern bool SetupDiSetDeviceRegistryPropertyW(IntPtr set, ref Info info, uint property,
        byte[] buffer, uint size);
    [DllImport("setupapi.dll", SetLastError=true)]
    static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);

    static IntPtr Open(string id, out Info info) {
        info = new Info { Size = (uint)Marshal.SizeOf(typeof(Info)) };
        IntPtr set = SetupDiCreateDeviceInfoList(IntPtr.Zero, IntPtr.Zero);
        if (set == new IntPtr(-1)) throw new Win32Exception(Marshal.GetLastWin32Error());
        if (!SetupDiOpenDeviceInfoW(set, id, IntPtr.Zero, 0, ref info)) {
            int error = Marshal.GetLastWin32Error();
            SetupDiDestroyDeviceInfoList(set);
            throw new Win32Exception(error);
        }
        return set;
    }
    public static byte[] Read(string id, uint property, out uint type) {
        Info info;
        IntPtr set = Open(id, out info);
        try {
            uint required;
            bool ok = SetupDiGetDeviceRegistryPropertyW(set, ref info, property, out type, null, 0, out required);
            int error = Marshal.GetLastWin32Error();
            // ERROR_INVALID_DATA is SetupAPI's absent-property result.
            if (!ok && error == 13) return null;
            if (!ok && error != 122) throw new Win32Exception(error);
            byte[] data = new byte[required];
            if (!SetupDiGetDeviceRegistryPropertyW(set, ref info, property, out type, data, required, out required))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            return data;
        } finally { SetupDiDestroyDeviceInfoList(set); }
    }
    public static void Write(string id, byte[] data) {
        Info info;
        IntPtr set = Open(id, out info);
        try {
            if (!SetupDiSetDeviceRegistryPropertyW(set, ref info, 12, data,
                data == null ? 0 : (uint)data.Length))
                throw new Win32Exception(Marshal.GetLastWin32Error());
        } finally { SetupDiDestroyDeviceInfoList(set); }
    }
}
'@
}

function Save-VerifiedBackup($Path, $Record) {
    # No -Force: never overwrite the only rollback copy.
    New-Item -ItemType File -Path $Path -ErrorAction Stop | Out-Null
    $Record | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding UTF8
    $saved = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($key in $Record.Keys) {
        if ($saved.$key -cne $Record[$key]) { throw "Backup verification failed for $key; no device change made." }
    }
}

[uint32]$type = 0
$bytes = [DeviceFriendlyName]::Read($Id, 12, [ref]$type)
$exists = $null -ne $bytes
$base64 = if ($exists) { [Convert]::ToBase64String($bytes) } else { $null }

if ($Action -eq 'Inspect') {
    [pscustomobject]@{
        DeviceInstanceId = $Id
        Exists = $exists
        RegistryType = $type
        OriginalBase64 = $base64
        MatchesEmptyRegSz = ($exists -and $type -eq 1 -and $base64 -ceq 'AAA=')
    }
    return
}

if ($Action -eq 'Repair') {
    if (-not $exists -or $type -ne 1 -or $bytes.Length -ne 2 -or
        $bytes[0] -ne 0 -or $bytes[1] -ne 0) {
        throw 'Expected existing REG_SZ bytes 00 00; absent or different property: stop.'
    }
    [uint32]$descriptionType = 0
    $description = [DeviceFriendlyName]::Read($Id, 0, [ref]$descriptionType)
    if ($null -eq $description -or $descriptionType -ne 1 -or
        [string]::IsNullOrWhiteSpace([Text.Encoding]::Unicode.GetString($description).Trim([char]0))) {
        throw 'No usable DeviceDesc fallback; stop.'
    }
    if (-not $PSCmdlet.ShouldProcess($Id, 'Back up and remove only the empty FriendlyName override')) { return }
    Save-VerifiedBackup $BackupPath ([ordered]@{
        DeviceInstanceId = $Id
        Property = 12
        RegistryType = $type
        OriginalBase64 = $base64
        OriginalState = 'Present'
    })
    # Fail closed if metadata changed while the backup was being written.
    [uint32]$currentType = 0
    $current = [DeviceFriendlyName]::Read($Id, 12, [ref]$currentType)
    if ($null -eq $current -or $currentType -ne 1 -or [Convert]::ToBase64String($current) -cne 'AAA=') {
        throw 'Property changed after backup; stop.'
    }
    [DeviceFriendlyName]::Write($Id, $null)
    if ($null -ne [DeviceFriendlyName]::Read($Id, 12, [ref]$currentType)) {
        throw 'Deletion could not be verified; preserve the backup and investigate.'
    }
    "Empty FriendlyName removed. Keep backup: $BackupPath"
    return
}

$saved = Get-Content -LiteralPath $BackupPath -Raw | ConvertFrom-Json
if ($saved.DeviceInstanceId -cne $Id -or $saved.Property -ne 12 -or
    $saved.RegistryType -ne 1 -or $saved.OriginalBase64 -cne 'AAA=' -or $saved.OriginalState -cne 'Present') {
    throw 'Backup identity, property, type or original bytes do not match; stop.'
}
if ($exists) { throw 'Rollback requires the override still to be absent; stop.' }
if (-not $PSCmdlet.ShouldProcess($Id, 'Restore the empty FriendlyName; this can reintroduce the hang')) { return }
Save-VerifiedBackup ($BackupPath + '.before-rollback.json') ([ordered]@{
    DeviceInstanceId = $Id
    Property = 12
    OriginalState = 'Absent'
})
if ($null -ne [DeviceFriendlyName]::Read($Id, 12, [ref]$type)) {
    throw 'Property changed after pre-rollback backup; stop.'
}
[DeviceFriendlyName]::Write($Id, [Convert]::FromBase64String($saved.OriginalBase64))
$restored = [DeviceFriendlyName]::Read($Id, 12, [ref]$type)
if ($null -eq $restored -or $type -ne 1 -or [Convert]::ToBase64String($restored) -cne 'AAA=') {
    throw 'Restore could not be verified; preserve both backups and investigate.'
}
'Original empty FriendlyName restored. Undo rollback with Repair and a new backup path.'
