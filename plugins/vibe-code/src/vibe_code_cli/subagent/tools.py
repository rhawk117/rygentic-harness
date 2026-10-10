import re

KNOWN_TOOLS = frozenset(
    {
        'Agent',
        'Artifact',
        'AskUserQuestion',
        'Bash',
        'CronCreate',
        'CronDelete',
        'CronList',
        'Edit',
        'EndConversation',
        'EnterPlanMode',
        'EnterWorktree',
        'ExitPlanMode',
        'ExitWorktree',
        'Glob',
        'Grep',
        'ListAgents',
        'ListMcpResourcesTool',
        'LSP',
        'Monitor',
        'NotebookEdit',
        'PowerShell',
        'PushNotification',
        'Read',
        'ReadMcpResourceTool',
        'RemoteTrigger',
        'ReportFindings',
        'ScheduleWakeup',
        'SendFeedback',
        'SendMessage',
        'SendUserFile',
        'ShareOnboardingGuide',
        'Skill',
        'SubagentHandback',
        'Task',
        'TaskCreate',
        'TaskGet',
        'TaskList',
        'TaskOutput',
        'TaskStop',
        'TaskUpdate',
        'TodoWrite',
        'ToolSearch',
        'WaitForMcpServers',
        'WebFetch',
        'WebSearch',
        'Workflow',
        'Write',
    }
)
MCP_TOOL = re.compile(r'mcp__[\w.*-]+')
COMMA_OUTSIDE_PARENTHESES = re.compile(r'(?:[^,(]|\([^)]*\))+')


def tool_entries(value: str | list[str] | None) -> list[str] | None:
    if value is None:
        return None
    
    entries = COMMA_OUTSIDE_PARENTHESES.findall(value) if isinstance(value, str) else value
    return [entry.strip() for entry in entries if entry.strip()]


def tool_name(entry: str) -> str:
    return entry.split('(', 1)[0].strip()


def is_known_tool(entry: str) -> bool:
    name = tool_name(entry)
    return name in KNOWN_TOOLS or MCP_TOOL.fullmatch(name) is not None
