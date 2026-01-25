/**
 * Issue Tracking Store
 *
 * Accumulates translation issues from QA checks and manual review.
 * Issues persist for the session and can be exported.
 */

import { writable, get } from 'svelte/store';

export interface Issue {
	id: string;
	segment_id: string;
	source: string;
	target: string;
	issue_type: string; // "qa_punctuation", "qa_numbers", "semantic", "terminology", etc.
	severity: 'error' | 'warning' | 'info';
	message: string;
	suggested_fix?: string;
	source_tool: 'qa_check' | 'manual_review' | 'rag_search';
	timestamp: number;
	resolved: boolean;
}

export const sessionIssues = writable<Issue[]>([]);

/**
 * Add an issue to the tracker with deduplication.
 * If same segment_id + issue_type exists and is unresolved, updates it instead.
 */
export function addIssue(issue: Omit<Issue, 'id' | 'timestamp' | 'resolved'>): void {
	sessionIssues.update((issues) => {
		// Check for existing unresolved issue with same segment + type
		const existingIndex = issues.findIndex(
			(i) =>
				i.segment_id === issue.segment_id &&
				i.issue_type === issue.issue_type &&
				!i.resolved
		);

		if (existingIndex !== -1) {
			// Update existing issue
			const updated = [...issues];
			updated[existingIndex] = {
				...updated[existingIndex],
				message: issue.message, // Use latest message
				suggested_fix: issue.suggested_fix ?? updated[existingIndex].suggested_fix,
				timestamp: Date.now()
			};
			return updated;
		}

		// Add new issue
		return [
			...issues,
			{
				...issue,
				id: crypto.randomUUID(),
				timestamp: Date.now(),
				resolved: false
			}
		];
	});
}

/**
 * Add multiple issues at once (used for QA auto-populate)
 */
export function addIssues(issues: Omit<Issue, 'id' | 'timestamp' | 'resolved'>[]): number {
	let added = 0;
	for (const issue of issues) {
		const before = get(sessionIssues).length;
		addIssue(issue);
		if (get(sessionIssues).length > before) added++;
	}
	return added;
}

/**
 * Mark an issue as resolved
 */
export function resolveIssue(id: string): void {
	sessionIssues.update((issues) =>
		issues.map((i) => (i.id === id ? { ...i, resolved: true } : i))
	);
}

/**
 * Mark an issue as unresolved
 */
export function unresolveIssue(id: string): void {
	sessionIssues.update((issues) =>
		issues.map((i) => (i.id === id ? { ...i, resolved: false } : i))
	);
}

/**
 * Clear all issues (new session)
 */
export function clearIssues(): void {
	sessionIssues.set([]);
}

/**
 * Get issue counts by status
 */
export function getIssueCounts(): { total: number; resolved: number; unresolved: number } {
	const issues = get(sessionIssues);
	const resolved = issues.filter((i) => i.resolved).length;
	return {
		total: issues.length,
		resolved,
		unresolved: issues.length - resolved
	};
}

/**
 * Export issues as Markdown
 */
export function exportAsMarkdown(): string {
	const issues = get(sessionIssues);
	if (issues.length === 0) return '# Translation Issues\n\nNo issues found.';

	const unresolved = issues.filter((i) => !i.resolved);
	const resolved = issues.filter((i) => i.resolved);

	// Group by type
	const byType = new Map<string, Issue[]>();
	for (const issue of unresolved) {
		const list = byType.get(issue.issue_type) || [];
		list.push(issue);
		byType.set(issue.issue_type, list);
	}

	let md = `# Translation Issues\n\n`;
	md += `**Total:** ${issues.length} | **Unresolved:** ${unresolved.length} | **Resolved:** ${resolved.length}\n\n`;

	if (unresolved.length > 0) {
		md += `## Unresolved Issues\n\n`;
		for (const [type, typeIssues] of byType) {
			md += `### ${formatIssueType(type)} (${typeIssues.length})\n\n`;
			for (const issue of typeIssues) {
				md += `- **Segment ${issue.segment_id}** [${issue.severity}]: ${issue.message}\n`;
				if (issue.source) md += `  - Source: "${truncate(issue.source, 80)}"\n`;
				if (issue.target) md += `  - Target: "${truncate(issue.target, 80)}"\n`;
				if (issue.suggested_fix) md += `  - Suggested: "${issue.suggested_fix}"\n`;
				md += `\n`;
			}
		}
	}

	if (resolved.length > 0) {
		md += `## Resolved Issues (${resolved.length})\n\n`;
		for (const issue of resolved) {
			md += `- ~~Segment ${issue.segment_id}: ${issue.message}~~\n`;
		}
	}

	return md;
}

/**
 * Export issues as CSV
 */
export function exportAsCsv(): string {
	const issues = get(sessionIssues);
	const headers = ['Segment ID', 'Type', 'Severity', 'Message', 'Source', 'Target', 'Suggested Fix', 'Status'];
	const rows = issues.map((i) => [
		i.segment_id,
		i.issue_type,
		i.severity,
		`"${i.message.replace(/"/g, '""')}"`,
		`"${(i.source || '').replace(/"/g, '""')}"`,
		`"${(i.target || '').replace(/"/g, '""')}"`,
		`"${(i.suggested_fix || '').replace(/"/g, '""')}"`,
		i.resolved ? 'Resolved' : 'Open'
	]);

	return [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
}

// Helpers

function formatIssueType(type: string): string {
	// "qa_punctuation" -> "Punctuation", "semantic" -> "Semantic"
	return type
		.replace(/^qa_/, '')
		.replace(/_/g, ' ')
		.replace(/\b\w/g, (c) => c.toUpperCase());
}

function truncate(s: string, len: number): string {
	return s.length > len ? s.slice(0, len - 3) + '...' : s;
}