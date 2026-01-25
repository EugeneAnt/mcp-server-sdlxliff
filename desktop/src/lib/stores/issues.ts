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
	skipped: boolean; // User chose to skip this (false positive, intentional, etc.)
	applied: boolean; // Fix was applied to the file
}

export const sessionIssues = writable<Issue[]>([]);

/**
 * Add an issue to the tracker with deduplication.
 *
 * Deduplication strategy:
 * - If issue has suggested_fix: dedupe by segment_id only (one fix per segment)
 * - If issue has no suggested_fix: dedupe by segment_id + issue_type (multiple observations OK)
 *
 * This ensures that when discussing fixes, later corrections update rather than duplicate.
 */
export function addIssue(issue: Omit<Issue, 'id' | 'timestamp' | 'skipped' | 'applied'>): void {
	sessionIssues.update((issues) => {
		let existingIndex = -1;

		if (issue.suggested_fix) {
			// Has a fix: dedupe by segment_id only (one actionable fix per segment)
			existingIndex = issues.findIndex(
				(i) =>
					i.segment_id === issue.segment_id &&
					i.suggested_fix && // also has a fix
					!i.skipped &&
					!i.applied
			);
		} else {
			// No fix (observation only): dedupe by segment_id + issue_type
			existingIndex = issues.findIndex(
				(i) =>
					i.segment_id === issue.segment_id &&
					i.issue_type === issue.issue_type &&
					!i.skipped &&
					!i.applied
			);
		}

		if (existingIndex !== -1) {
			// Update existing issue
			const updated = [...issues];
			updated[existingIndex] = {
				...updated[existingIndex],
				issue_type: issue.issue_type, // Update type if refined
				message: issue.message, // Use latest message
				suggested_fix: issue.suggested_fix ?? updated[existingIndex].suggested_fix,
				source: issue.source || updated[existingIndex].source,
				target: issue.target || updated[existingIndex].target,
				severity: issue.severity,
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
				skipped: false,
				applied: false
			}
		];
	});
}

/**
 * Add multiple issues at once (used for QA auto-populate)
 */
export function addIssues(issues: Omit<Issue, 'id' | 'timestamp' | 'skipped' | 'applied'>[]): number {
	let added = 0;
	for (const issue of issues) {
		const before = get(sessionIssues).length;
		addIssue(issue);
		if (get(sessionIssues).length > before) added++;
	}
	return added;
}

/**
 * Mark an issue as skipped (won't be applied in batch)
 */
export function skipIssue(id: string): void {
	sessionIssues.update((issues) =>
		issues.map((i) => (i.id === id ? { ...i, skipped: true } : i))
	);
}

/**
 * Unskip an issue (will be included in batch apply)
 */
export function unskipIssue(id: string): void {
	sessionIssues.update((issues) =>
		issues.map((i) => (i.id === id ? { ...i, skipped: false } : i))
	);
}

/**
 * Mark an issue as applied (fix was written to file)
 */
export function markIssueApplied(id: string): void {
	sessionIssues.update((issues) =>
		issues.map((i) => (i.id === id ? { ...i, applied: true } : i))
	);
}

/**
 * Get all issues that can be applied (not skipped, not applied, has suggested_fix)
 */
export function getApplicableIssues(): Issue[] {
	return get(sessionIssues).filter((i) => !i.skipped && !i.applied && i.suggested_fix);
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
export function getIssueCounts(): {
	total: number;
	pending: number;
	skipped: number;
	applied: number;
	applicable: number;
} {
	const issues = get(sessionIssues);
	const skipped = issues.filter((i) => i.skipped).length;
	const applied = issues.filter((i) => i.applied).length;
	const applicable = issues.filter((i) => !i.skipped && !i.applied && i.suggested_fix).length;
	return {
		total: issues.length,
		pending: issues.length - skipped - applied,
		skipped,
		applied,
		applicable
	};
}

/**
 * Export issues as Markdown
 */
export function exportAsMarkdown(): string {
	const issues = get(sessionIssues);
	if (issues.length === 0) return '# Translation Issues\n\nNo issues found.';

	const pending = issues.filter((i) => !i.skipped && !i.applied);
	const applied = issues.filter((i) => i.applied);
	const skipped = issues.filter((i) => i.skipped);

	// Group pending by type
	const byType = new Map<string, Issue[]>();
	for (const issue of pending) {
		const list = byType.get(issue.issue_type) || [];
		list.push(issue);
		byType.set(issue.issue_type, list);
	}

	let md = `# Translation Issues\n\n`;
	md += `**Total:** ${issues.length} | **Pending:** ${pending.length} | **Applied:** ${applied.length} | **Skipped:** ${skipped.length}\n\n`;

	if (pending.length > 0) {
		md += `## Pending Issues\n\n`;
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

	if (applied.length > 0) {
		md += `## Applied Fixes (${applied.length})\n\n`;
		for (const issue of applied) {
			md += `- ✓ Segment ${issue.segment_id}: ${issue.message}\n`;
		}
		md += '\n';
	}

	if (skipped.length > 0) {
		md += `## Skipped Issues (${skipped.length})\n\n`;
		for (const issue of skipped) {
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
	const rows = issues.map((i) => {
		let status = 'Pending';
		if (i.applied) status = 'Applied';
		else if (i.skipped) status = 'Skipped';
		return [
			i.segment_id,
			i.issue_type,
			i.severity,
			`"${i.message.replace(/"/g, '""')}"`,
			`"${(i.source || '').replace(/"/g, '""')}"`,
			`"${(i.target || '').replace(/"/g, '""')}"`,
			`"${(i.suggested_fix || '').replace(/"/g, '""')}"`,
			status
		];
	});

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