from crewai import Agent
from core.file_system import FileWriteTool, FileReadTool

file_writer = FileWriteTool()
file_reader = FileReadTool()

def create_tl(llm_model):
    return Agent(
        role='Team Lead',
        goal='Convert the PRD and Architecture into a strictly defined Task List.',
        backstory="""You are the technical strategist. You read the PRD and Architecture created by the PM, 
        and you break it down into a granular JSON Task List that developers can execute step-by-step.""",
        tools=[file_writer, file_reader],
        verbose=False,
        allow_delegation=False,
        llm=llm_model
    )
