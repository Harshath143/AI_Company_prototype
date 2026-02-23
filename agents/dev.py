from crewai import Agent
from core.file_system import FileWriteTool, FileReadTool, DirectoryListTool

file_writer = FileWriteTool()
file_reader = FileReadTool()
dir_lister = DirectoryListTool()

def create_dev(llm_model):
    return Agent(
        role='Developer',
        goal='Write clean, efficient, and modular code to fulfill tasks.',
        backstory="""You are a top-tier software developer. You execute tasks from the Task List one by one. 
        You write code that is production-ready, well-documented, and adheres to the architecture.""",
        tools=[file_writer, file_reader, dir_lister],
        verbose=False,
        allow_delegation=False,
        llm=llm_model
    )
