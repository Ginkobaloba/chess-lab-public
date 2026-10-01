# Provenance: copied from Ginkobaloba/draughts-lab web/scripts/cpu-cap.ps1 at commit
# 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT). Changes: the
# examples name chess-lab scripts; the Job Object type is renamed ChessLabJobCap; the logic is unchanged.
<#
.SYNOPSIS
  Runs a command under a hard CPU cap (a Windows Job Object), the supported
  way to approximate a slow device for the in-browser model.

.DESCRIPTION
  Chromium's CPU throttling (CDP Emulation.setCPUThrottlingRate) does not
  reach a dedicated worker (draughts-lab measured this on Chromium 148), and
  the model runs in one. A Job Object hard cap limits every process in the
  job, Node and Chromium (its renderer and worker threads included), to a
  share of total CPU time. On Linux the equivalent is a cgroup v2 `cpu.max`
  (for example `systemd-run --user --scope -p CPUQuota=25% <command>`).

  The cap is a share of ALL logical CPUs: -Cores 0.25 on a 32-thread machine
  is a quarter of one thread in total, spread over whatever the job runs. A
  capped run reports its own per-move evaluation times; those measured times,
  not the cap, are what to compare with a device.

.EXAMPLE
  powershell -File scripts/cpu-cap.ps1 -Cores 0.25 -Command 'node scripts/e2e.mjs --phase timing'
#>
param(
  [Parameter(Mandatory = $true)][double]$Cores,
  [Parameter(Mandatory = $true)][string]$Command,
  [string]$WorkDir = '',
  [string]$LogFile = ''
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 does not set $PSScriptRoot for parameter defaults.
if (-not $WorkDir) { $WorkDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$logical = [Environment]::ProcessorCount
# CpuRate is cycles per 10,000 of all logical CPUs (JOBOBJECT_CPU_RATE_CONTROL_INFORMATION), 1..10000.
$rate = [uint32][Math]::Max(1, [Math]::Min(10000, [Math]::Round($Cores / $logical * 10000)))

if (-not ('ChessLabJobCap' -as [type])) {
  Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class ChessLabJobCap {
  [StructLayout(LayoutKind.Sequential)]
  public struct CpuRate { public uint ControlFlags; public uint Rate; }
  [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
  static extern IntPtr CreateJobObject(IntPtr attributes, string name);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref CpuRate info, uint length);
  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
  public static IntPtr Create(uint rate) {
    IntPtr job = CreateJobObject(IntPtr.Zero, null);
    if (job == IntPtr.Zero) throw new Exception("CreateJobObject failed: " + Marshal.GetLastWin32Error());
    CpuRate info = new CpuRate();
    info.ControlFlags = 0x1 | 0x4; // JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | _HARD_CAP
    info.Rate = rate;
    // 15 = JobObjectCpuRateControlInformation
    if (!SetInformationJobObject(job, 15, ref info, (uint)Marshal.SizeOf(info))) {
      throw new Exception("SetInformationJobObject failed: " + Marshal.GetLastWin32Error());
    }
    return job;
  }
}
"@
}

$job = [ChessLabJobCap]::Create($rate)
# The child waits before running the command so it is inside the job before it starts anything;
# processes it starts (node, Chromium) inherit the job.
$redirect = if ($LogFile) { " *> '$LogFile'" } else { '' }
$inner = "Start-Sleep -Seconds 2; Set-Location '$WorkDir'; $Command$redirect; exit `$LASTEXITCODE"
$child = Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', $inner) -NoNewWindow -PassThru
if (-not [ChessLabJobCap]::AssignProcessToJobObject($job, $child.Handle)) {
  $child.Kill()
  throw 'AssignProcessToJobObject failed'
}
try { $child.PriorityClass = 'BelowNormal' } catch { }
Write-Host ("cpu-cap: pid {0}, rate {1}/10000 of {2} logical CPUs (= {3} of one CPU)" -f $child.Id, $rate, $logical, [Math]::Round($rate / 10000 * $logical, 3))
$child.WaitForExit()
Write-Host "cpu-cap: exit $($child.ExitCode)"
exit $child.ExitCode
