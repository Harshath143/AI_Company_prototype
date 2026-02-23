from crewai import Agent
from core.file_system import FileWriteTool, FileReadTool, DirectoryListTool

file_writer = FileWriteTool()
file_reader = FileReadTool()
dir_lister = DirectoryListTool()

def create_tester(llm_model):
    return Agent(
        role='QA Tester',
        goal='Create and run unit tests to verify the code.',
        backstory="""You are a rigorous QA engineer. You write unit tests (using pytest or unittest) for the code produced by the Developer. 
        You ensure 90% coverage and that all edge cases are handled.""",
        tools=[file_writer, file_reader, dir_lister],
        verbose=False,
        allow_delegation=False,
        llm=llm_model
    )
