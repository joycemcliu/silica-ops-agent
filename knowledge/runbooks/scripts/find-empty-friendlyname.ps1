<#
Read-only candidate scan across all present Windows device classes.
Never executed end-to-end in this session; native enumeration was used in the incident.
An empty result is inconclusive if any device/property query fails.
#>
#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run this script on the affected Windows server.' }
$failures = 0
Get-PnpDevice -PresentOnly -ErrorAction Stop | ForEach-Object {
    $device = $_
    try {
        $properties = @(Get-PnpDeviceProperty -InstanceId $device.InstanceId -ErrorAction Stop)
        $name = $properties | Where-Object KeyName -eq 'DEVPKEY_Device_FriendlyName'
        if ($null -ne $name -and $name.Type -eq 'String' -and
            [string]::IsNullOrEmpty([string]$name.Data)) {
            [pscustomobject]@{
                InstanceId = $device.InstanceId
                Class = $device.Class
                DeviceDescription = ($properties |
                    Where-Object KeyName -eq 'DEVPKEY_Device_DeviceDesc').Data
            }
        }
    } catch {
        $failures++
        Write-Warning "Could not inspect $($device.InstanceId): $_"
    }
}
if ($failures -gt 0) { throw 'Scan incomplete: resolve query failures before interpreting the results.' }
