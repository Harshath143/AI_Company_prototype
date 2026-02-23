import os
from core.logger import logger

# N-3 (Round 2): Single source of truth for project subdirectories
PROJECT_SUBDIRS = ("src", "tests", "frontend", "logs")

class FileSystem:
    @staticmethod
    def _assert_within_root(abs_path: str, path: str, action: str, project_root: str) -> str | None:
        """
        Returns an error string if abs_path is outside project_root, else None.
        C-2 (Round 2): accepts explicit project_root instead of os.getcwd()
        so this is safe even in multi-threaded / multi-run scenarios.
        """
        try:
            # commonpath() correctly handles Windows paths and the prefix-bypass attack
            # e.g. 'C:\projects\AI_company_evil' passes startswith but fails commonpath
            if os.path.commonpath([abs_path, project_root]) != project_root:
                logger.error(f"Security Alert: Path traversal on {action}: {path}")
                return f"Error: Security violation. Cannot {action} outside project root."
        except ValueError:
            # commonpath raises ValueError on mixed drive letters on Windows
            logger.error(f"Security Alert: Cross-drive path traversal on {action}: {path}")
            return f"Error: Security violation. Cannot {action} outside project root."
        return None

    @staticmethod
    def write_file(path: str, content: str, project_root: str = None) -> str:
        try:
            root = project_root or os.getcwd()
            abs_path = os.path.abspath(os.path.join(root, path))
            err = FileSystem._assert_within_root(abs_path, path, "write", root)
            if err:
                return err

            # Ensure directory exists
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"FileSystem: Wrote to {abs_path}")
            return f"Successfully wrote to {path}"
        except Exception as e:
            logger.error(f"FileSystem: Error writing to {path} - {e}")
            return f"Error writing file: {str(e)}"

    @staticmethod
    def read_file(path: str, project_root: str = None) -> str:
        try:
            root = project_root or os.getcwd()
            abs_path = os.path.abspath(os.path.join(root, path))
            err = FileSystem._assert_within_root(abs_path, path, "read", root)
            if err:
                return err
            if not os.path.exists(abs_path):
                return f"Error: File {path} does not exist."
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.info(f"FileSystem: Read from {abs_path}")
            return content
        except Exception as e:
            logger.error(f"FileSystem: Error reading {path} - {e}")
            return f"Error reading file: {str(e)}"

    @staticmethod
    def list_dir(path: str, project_root: str = None) -> str:
        try:
            root = project_root or os.getcwd()
            abs_path = os.path.abspath(os.path.join(root, path))
            if not os.path.exists(abs_path):
                return f"Error: Directory {path} does not exist."
            files = os.listdir(abs_path)
            return "\n".join(files)
        except Exception as e:
            return f"Error listing directory: {str(e)}"


# CrewAI Tool Wrappers (legacy — kept for agents/ compatibility)
try:
    from crewai.tools import BaseTool

    class FileWriteTool(BaseTool):
        name: str = "Write File"
        description: str = "Writes content to a file at a specific path. Args: path (str), content (str)"

        def _run(self, path: str, content: str) -> str:
            return FileSystem.write_file(path, content)

    class FileReadTool(BaseTool):
        name: str = "Read File"
        description: str = "Reads content from a file. Args: path (str)"

        def _run(self, path: str) -> str:
            return FileSystem.read_file(path)

    class DirectoryListTool(BaseTool):
        name: str = "List Directory"
        description: str = "Lists files in a directory. Args: path (str)"

        def _run(self, path: str) -> str:
            return FileSystem.list_dir(path)

except ImportError:
    pass  # crewai not required when using groq_runner directly
