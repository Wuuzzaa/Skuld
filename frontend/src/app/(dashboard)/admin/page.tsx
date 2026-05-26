'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { LoadingState } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

// API functions
async function getLogComponents() {
  const { data } = await api.get('/admin/logs/components');
  return data;
}

async function getLogDates(component: string) {
  const { data } = await api.get(`/admin/logs/dates/${component}`);
  return data;
}

async function getLogFiles(component: string, date: string) {
  const { data } = await api.get(`/admin/logs/files/${component}/${date}`);
  return data;
}

async function getLogContent(component: string, date: string, filename: string, level: string, search: string) {
  const { data } = await api.get(`/admin/logs/content/${component}/${date}/${filename}`, {
    params: { level, search, tail: 500 },
  });
  return data;
}

async function tailLog(component: string, date: string, filename: string, sinceLine: number) {
  const { data } = await api.get(`/admin/logs/tail/${component}/${date}/${filename}`, {
    params: { since_line: sinceLine, limit: 200 },
  });
  return data;
}

async function getLatestLog(component: string) {
  const { data } = await api.get(`/admin/logs/latest/${component}`);
  return data;
}

async function getJobModes() {
  const { data } = await api.get('/admin/jobs/modes');
  return data;
}

async function triggerJob(mode: string) {
  const { data } = await api.post('/admin/jobs/trigger', { mode });
  return data;
}

async function getRunningJobs() {
  const { data } = await api.get('/admin/jobs/running');
  return data;
}

async function getActivity(hours: number, table: string) {
  const { data } = await api.get('/admin/activity', { params: { hours, table: table || undefined } });
  return data;
}

async function getActivityTables() {
  const { data } = await api.get('/admin/activity/tables');
  return data;
}

async function getSchedule() {
  const { data } = await api.get('/admin/schedule');
  return data;
}

async function getJobHistory(days: number, modeFilter: string) {
  const { data } = await api.get('/admin/jobs/history', {
    params: { days, mode_filter: modeFilter || undefined },
  });
  return data;
}

type Tab = 'logs' | 'jobs' | 'activity' | 'history';

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>('jobs');

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Admin - Job Management</h1>

      {/* Tab buttons */}
      <div className="flex gap-1 border-b border-border pb-0">
        {(['jobs', 'history', 'logs', 'activity'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-t-lg transition-colors',
              activeTab === tab
                ? 'bg-primary/10 text-primary border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
            )}
          >
            {tab === 'logs' ? 'Log Viewer' : tab === 'jobs' ? 'Trigger Jobs' : tab === 'history' ? 'Job History' : 'Recent Activity'}
          </button>
        ))}
      </div>

      {activeTab === 'logs' && <LogViewer />}
      {activeTab === 'jobs' && <JobTrigger />}
      {activeTab === 'history' && <JobHistory />}
      {activeTab === 'activity' && <ActivityView />}
    </div>
  );
}

// ==============================================================================
// LOG VIEWER
// ==============================================================================
function LogViewer() {
  const [component, setComponent] = useState('');
  const [date, setDate] = useState('');
  const [file, setFile] = useState('');
  const [level, setLevel] = useState('ERROR,WARNING,INFO');
  const [search, setSearch] = useState('');

  const { data: components } = useQuery({
    queryKey: ['admin-log-components'],
    queryFn: getLogComponents,
  });

  const { data: dates } = useQuery({
    queryKey: ['admin-log-dates', component],
    queryFn: () => getLogDates(component),
    enabled: !!component,
  });

  const { data: files } = useQuery({
    queryKey: ['admin-log-files', component, date],
    queryFn: () => getLogFiles(component, date),
    enabled: !!component && !!date,
  });

  const { data: logContent, isLoading: loadingContent, refetch: refetchLog } = useQuery({
    queryKey: ['admin-log-content', component, date, file, level, search],
    queryFn: () => getLogContent(component, date, file, level, search),
    enabled: !!component && !!date && !!file,
  });

  // Auto-select first available values
  if (components?.length && !component) setComponent(components[0]);
  if (dates?.length && !date) setDate(dates[0]);
  if (files?.length && !file) setFile(files[0]);

  return (
    <div className="space-y-4">
      {/* Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Component</label>
          <select
            value={component}
            onChange={(e) => { setComponent(e.target.value); setDate(''); setFile(''); }}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            {components?.map((c: string) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Date</label>
          <select
            value={date}
            onChange={(e) => { setDate(e.target.value); setFile(''); }}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            {dates?.map((d: string) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Log File</label>
          <select
            value={file}
            onChange={(e) => setFile(e.target.value)}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            {files?.map((f: string) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Level Filter</label>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value="ERROR,WARNING,INFO,DEBUG">All</option>
            <option value="ERROR,WARNING,INFO">INFO+</option>
            <option value="ERROR,WARNING">Warnings & Errors</option>
            <option value="ERROR">Errors only</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Search</label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. timeout, OOM, failed..."
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* Log content */}
      {loadingContent ? (
        <LoadingState message="Loading logs..." />
      ) : logContent ? (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-muted-foreground">
              {logContent.displayed_lines} / {logContent.total_lines} lines
            </p>
            <button
              onClick={() => refetchLog()}
              className="text-xs text-muted-foreground hover:text-foreground border border-border rounded px-2 py-1"
            >
              Refresh
            </button>
          </div>
          <pre className="bg-card border border-border rounded-lg p-4 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap">
            {logContent.content.map((line: string, i: number) => (
              <div
                key={i}
                className={cn(
                  'py-0.5',
                  line.includes('ERROR') && 'text-red-400',
                  line.includes('WARNING') && 'text-yellow-400',
                )}
              >
                {line}
              </div>
            ))}
          </pre>
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">Select a log file to view.</p>
      )}

      {/* Schedule reference */}
      <ScheduleReference />
    </div>
  );
}

// ==============================================================================
// JOB TRIGGER with Live Log
// ==============================================================================
function JobTrigger() {
  const [selectedMode, setSelectedMode] = useState('');
  const queryClient = useQueryClient();

  // Live log state
  const [liveLog, setLiveLog] = useState<{
    component: string;
    date: string;
    filename: string;
    mode: string;
  } | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [isLiveViewing, setIsLiveViewing] = useState(false);
  const [sinceLineRef] = useState({ current: 0 });
  const logEndRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: modes } = useQuery({
    queryKey: ['admin-job-modes'],
    queryFn: getJobModes,
  });

  const { data: running, refetch: refetchRunning } = useQuery({
    queryKey: ['admin-running-jobs'],
    queryFn: getRunningJobs,
    refetchInterval: isLiveViewing ? 5000 : 10000,
  });

  // Auto-scroll when new lines appear
  useEffect(() => {
    if (logEndRef.current && isLiveViewing) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logLines, isLiveViewing]);

  // Polling logic - resolves actual filename via /latest endpoint if predicted file not found
  const startPolling = useCallback((component: string, date: string, filename: string) => {
    if (intervalRef.current) clearInterval(intervalRef.current);

    sinceLineRef.current = 0;
    setLogLines([]);
    setIsLiveViewing(true);

    let resolvedFile = filename;
    let resolvedDate = date;
    let retryCount = 0;

    const poll = async () => {
      try {
        const data = await tailLog(component, resolvedDate, resolvedFile, sinceLineRef.current);
        if (data.lines?.length > 0) {
          setLogLines(prev => [...prev, ...data.lines]);
          sinceLineRef.current += data.lines.length;
          retryCount = 0;
        } else if (data.total_lines === 0 && retryCount < 15) {
          // File not found or empty — try to find the actual latest log
          retryCount++;
          if (retryCount >= 3) {
            try {
              const latest = await getLatestLog(component);
              if (latest?.filename && latest.filename !== resolvedFile) {
                resolvedFile = latest.filename;
                resolvedDate = latest.date;
                sinceLineRef.current = 0;
                // Update the liveLog state so UI shows correct filename
                setLiveLog(prev => prev ? { ...prev, filename: resolvedFile, date: resolvedDate } : prev);
              }
            } catch {
              // ignore
            }
          }
        }
      } catch {
        // File may not exist yet, keep polling
        retryCount++;
      }
    };

    // First poll after a short delay (give the job time to create the file)
    setTimeout(poll, 1500);
    intervalRef.current = setInterval(poll, 2000);
  }, [sinceLineRef]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsLiveViewing(false);
  }, []);

  // Auto-stop polling when job finishes
  useEffect(() => {
    if (!isLiveViewing || !liveLog) return;
    const jobStillRunning = running?.some((j: any) => j.mode === liveLog.mode && j.alive);
    // Only stop if we've been polling for a while and job is gone
    if (running && !jobStillRunning && logLines.length > 0) {
      // Give it a few more seconds to flush final lines
      const timeout = setTimeout(() => stopPolling(), 5000);
      return () => clearTimeout(timeout);
    }
  }, [running, isLiveViewing, liveLog, logLines.length, stopPolling]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const trigger = useMutation({
    mutationFn: (mode: string) => triggerJob(mode),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-running-jobs'] });
      // Start live log viewing
      if (data?.component && data?.date && data?.filename) {
        setLiveLog({ component: data.component, date: data.date, filename: data.filename, mode: data.mode });
        startPolling(data.component, data.date, data.filename);
      }
    },
  });

  return (
    <div className="space-y-6">
      {/* Trigger section */}
      <div className="bg-card border border-border rounded-lg p-4 space-y-4">
        <h3 className="text-sm font-semibold">Trigger a Job</h3>
        <p className="text-xs text-muted-foreground">
          Jobs run inside the skuld-backend container. The process is started in the background.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
          <div className="md:col-span-2">
            <label className="text-xs text-muted-foreground mb-1 block">Job Mode</label>
            <select
              value={selectedMode}
              onChange={(e) => setSelectedMode(e.target.value)}
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm"
            >
              <option value="">-- Select a job --</option>
              {modes?.map((m: any) => (
                <option key={m.mode} value={m.mode}>
                  {m.mode} — {m.description}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() => { if (selectedMode) trigger.mutate(selectedMode); }}
            disabled={!selectedMode || trigger.isPending}
            className={cn(
              'px-4 py-2 rounded-md text-sm font-medium transition-colors',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {trigger.isPending ? 'Starting...' : 'Start Job'}
          </button>
        </div>

        {trigger.isSuccess && !isLiveViewing && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3 py-2 rounded-md text-sm">
            Job <strong>{trigger.data?.mode}</strong> triggered (PID: {trigger.data?.pid}).
          </div>
        )}
        {trigger.isError && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-3 py-2 rounded-md text-sm">
            Failed: {(trigger.error as any)?.response?.data?.detail || 'Unknown error'}
          </div>
        )}
      </div>

      {/* Live Log Panel */}
      {(isLiveViewing || logLines.length > 0) && liveLog && (
        <div className="bg-card border border-border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-semibold">Live Log Output</h3>
              {isLiveViewing && (
                <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  Streaming — {liveLog.mode}
                </span>
              )}
              {!isLiveViewing && (
                <span className="text-xs text-muted-foreground">Stopped</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{logLines.length} lines</span>
              {isLiveViewing ? (
                <button
                  onClick={stopPolling}
                  className="px-2 py-1 text-xs bg-red-500/20 text-red-400 border border-red-500/30 rounded hover:bg-red-500/30"
                >
                  Stop
                </button>
              ) : (
                <button
                  onClick={() => startPolling(liveLog.component, liveLog.date, liveLog.filename)}
                  className="px-2 py-1 text-xs bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded hover:bg-emerald-500/30"
                >
                  Resume
                </button>
              )}
              <button
                onClick={() => { stopPolling(); setLogLines([]); setLiveLog(null); }}
                className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
              >
                Close
              </button>
            </div>
          </div>

          <pre className="bg-background border border-border rounded-lg p-3 text-xs font-mono overflow-auto max-h-[500px] whitespace-pre-wrap">
            {logLines.length === 0 ? (
              <span className="text-muted-foreground">Waiting for log output...</span>
            ) : (
              logLines.map((line, i) => (
                <div
                  key={i}
                  className={cn(
                    'py-0.5',
                    line.includes('ERROR') && 'text-red-400',
                    line.includes('WARNING') && 'text-yellow-400',
                    line.includes('SUCCESS') && 'text-emerald-400',
                  )}
                >
                  {line}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </pre>
        </div>
      )}

      {/* Running jobs */}
      <div className="bg-card border border-border rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Running Jobs</h3>
          <button
            onClick={() => refetchRunning()}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Refresh
          </button>
        </div>

        {running?.length ? (
          <div className="space-y-2">
            {running.map((job: any) => {
              const elapsed = job.started_at
                ? Math.floor((Date.now() - new Date(job.started_at).getTime()) / 1000)
                : null;
              const elapsedStr = elapsed !== null
                ? elapsed >= 3600
                  ? `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`
                  : elapsed >= 60
                    ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
                    : `${elapsed}s`
                : null;
              const startStr = job.started_at
                ? new Date(job.started_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
                : null;
              return (
                <div key={job.mode} className="flex items-center gap-3 text-sm">
                  <span className={cn(
                    'w-2 h-2 rounded-full',
                    job.alive ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'
                  )} />
                  <span className="font-mono">{job.mode}</span>
                  <span className="text-muted-foreground">PID: {job.pid}</span>
                  <span className={job.alive ? 'text-emerald-400' : 'text-red-400'}>
                    {job.alive ? 'running' : 'stale lockfile'}
                  </span>
                  {startStr && (
                    <span className="text-muted-foreground text-xs">
                      Started: {startStr}{elapsedStr && ` | ${elapsedStr}`}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No jobs currently running.</p>
        )}
      </div>

      <ScheduleReference />
    </div>
  );
}

// ==============================================================================
// ACTIVITY VIEW
// ==============================================================================
function ActivityView() {
  const [hours, setHours] = useState(24);
  const [table, setTable] = useState('');

  const { data: tables } = useQuery({
    queryKey: ['admin-activity-tables'],
    queryFn: getActivityTables,
  });

  const { data: activity, isLoading } = useQuery({
    queryKey: ['admin-activity', hours, table],
    queryFn: () => getActivity(hours, table),
  });

  const totalRows = activity?.reduce((sum: number, row: any) => sum + (row.affected_rows || 0), 0) || 0;
  const uniqueTables = new Set(activity?.map((r: any) => r.table_name)).size;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Time Range</label>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value={6}>Last 6 hours</option>
            <option value={12}>Last 12 hours</option>
            <option value={24}>Last 24 hours</option>
            <option value={48}>Last 2 days</option>
            <option value={72}>Last 3 days</option>
            <option value={168}>Last 7 days</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Table</label>
          <select
            value={table}
            onChange={(e) => setTable(e.target.value)}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value="">All tables</option>
            {tables?.map((t: string) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-card border border-border rounded-lg p-3 text-center">
          <p className="text-2xl font-bold">{activity?.length || 0}</p>
          <p className="text-xs text-muted-foreground">Operations</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-3 text-center">
          <p className="text-2xl font-bold">{totalRows.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">Rows Affected</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-3 text-center">
          <p className="text-2xl font-bold">{uniqueTables}</p>
          <p className="text-xs text-muted-foreground">Tables Touched</p>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <LoadingState message="Loading activity..." />
      ) : activity?.length ? (
        <div className="overflow-auto max-h-[500px] border border-border rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-card sticky top-0">
              <tr className="border-b border-border">
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Timestamp</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Operation</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Table</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Rows</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Details</th>
              </tr>
            </thead>
            <tbody>
              {activity.map((row: any, i: number) => (
                <tr key={i} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="px-3 py-1.5 font-mono text-xs">{row.timestamp}</td>
                  <td className="px-3 py-1.5">
                    <span className={cn(
                      'px-1.5 py-0.5 rounded text-xs',
                      row.operation_type === 'INSERT' && 'bg-emerald-500/20 text-emerald-400',
                      row.operation_type === 'UPDATE' && 'bg-blue-500/20 text-blue-400',
                      row.operation_type === 'DELETE' && 'bg-red-500/20 text-red-400',
                      row.operation_type === 'TRUNCATE' && 'bg-yellow-500/20 text-yellow-400',
                    )}>
                      {row.operation_type}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">{row.table_name}</td>
                  <td className="px-3 py-1.5 text-right">{row.affected_rows?.toLocaleString()}</td>
                  <td className="px-3 py-1.5 text-xs text-muted-foreground truncate max-w-[200px]">
                    {row.additional_data}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">No activity in the selected time range.</p>
      )}
    </div>
  );
}

// ==============================================================================
// JOB HISTORY
// ==============================================================================
function JobHistory() {
  const [days, setDays] = useState(14);
  const [modeFilter, setModeFilter] = useState('');
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const { data: history, isLoading } = useQuery({
    queryKey: ['admin-job-history', days, modeFilter],
    queryFn: () => getJobHistory(days, modeFilter),
  });

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      success: 'bg-emerald-500/20 text-emerald-400',
      failed: 'bg-red-500/20 text-red-400',
      partial: 'bg-yellow-500/20 text-yellow-400',
      timeout: 'bg-orange-500/20 text-orange-400',
      oom: 'bg-red-500/20 text-red-400',
      unknown: 'bg-zinc-500/20 text-zinc-400',
    };
    const labels: Record<string, string> = {
      success: 'OK',
      failed: 'FAILED',
      partial: 'PARTIAL',
      timeout: 'TIMEOUT',
      oom: 'OOM',
      unknown: '?',
    };
    return (
      <span className={cn('px-1.5 py-0.5 rounded text-xs font-medium', styles[status] || styles.unknown)}>
        {labels[status] || status}
      </span>
    );
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds == null) return '-';
    if (seconds >= 3600) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${seconds}s`;
  };

  // Stats
  const totalRuns = history?.length || 0;
  const successRuns = history?.filter((h: any) => h.status === 'success').length || 0;
  const failedRuns = history?.filter((h: any) => ['failed', 'timeout', 'oom'].includes(h.status)).length || 0;
  const modes: string[] = history
    ? [...new Set(history.map((h: any) => h.mode))] as string[]
    : [];

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Time Range</label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value={3}>Last 3 days</option>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Job Mode</label>
          <select
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value)}
            className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value="">All modes</option>
            {modes.map((m: string) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-card border border-border rounded-lg p-3 text-center">
          <p className="text-2xl font-bold">{totalRuns}</p>
          <p className="text-xs text-muted-foreground">Total Runs</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-emerald-400">{successRuns}</p>
          <p className="text-xs text-muted-foreground">Successful</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-red-400">{failedRuns}</p>
          <p className="text-xs text-muted-foreground">Failed</p>
        </div>
      </div>

      {/* History table */}
      {isLoading ? (
        <LoadingState message="Loading job history..." />
      ) : history?.length ? (
        <div className="overflow-auto max-h-[600px] border border-border rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-card sticky top-0">
              <tr className="border-b border-border">
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Date</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Started</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Mode</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Status</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Duration</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Lines</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Size</th>
              </tr>
            </thead>
            <tbody>
              {history.map((run: any, i: number) => {
                const startTime = new Date(run.started_at).toLocaleTimeString('de-DE', {
                  hour: '2-digit', minute: '2-digit',
                });
                return (
                  <React.Fragment key={i}>
                    <tr
                      className={cn(
                        'border-b border-border/50 hover:bg-accent/30 cursor-pointer',
                        expandedRow === i && 'bg-accent/20'
                      )}
                      onClick={() => setExpandedRow(expandedRow === i ? null : i)}
                    >
                      <td className="px-3 py-1.5 font-mono text-xs">{run.date}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{startTime}</td>
                      <td className="px-3 py-1.5">
                        <span className="font-mono text-xs">{run.mode}</span>
                      </td>
                      <td className="px-3 py-1.5">{statusBadge(run.status)}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">
                        {formatDuration(run.duration_seconds)}
                      </td>
                      <td className="px-3 py-1.5 text-right text-xs text-muted-foreground">
                        {run.total_lines?.toLocaleString()}
                      </td>
                      <td className="px-3 py-1.5 text-right text-xs text-muted-foreground">
                        {run.file_size_kb} KB
                      </td>
                    </tr>
                    {expandedRow === i && run.error_summary && (
                      <tr className="border-b border-border/50">
                        <td colSpan={7} className="px-3 py-2">
                          <div className="bg-red-500/5 border border-red-500/20 rounded-md p-3">
                            <p className="text-xs font-medium text-red-400 mb-1">Errors:</p>
                            <pre className="text-xs font-mono text-red-300/80 whitespace-pre-wrap">
                              {run.error_summary}
                            </pre>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">No job runs found in the selected time range.</p>
      )}
    </div>
  );
}

// ==============================================================================
// SCHEDULE REFERENCE (shared)
// ==============================================================================
function ScheduleReference() {
  const { data: schedule } = useQuery({
    queryKey: ['admin-schedule'],
    queryFn: getSchedule,
  });

  return (
    <details className="bg-card border border-border rounded-lg p-3">
      <summary className="text-sm font-medium cursor-pointer">Cron Schedule Reference</summary>
      <div className="mt-3 space-y-1">
        {schedule?.map((s: any) => (
          <div key={s.mode} className="flex gap-3 text-xs">
            <code className="text-muted-foreground w-40">{s.schedule}</code>
            <span className="font-medium">{s.mode}</span>
            <span className="text-muted-foreground">{s.description}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
