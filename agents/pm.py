from crewai import Agent
from core.file_system import FileWriteTool, FileReadTool

file_writer = FileWriteTool()
file_reader = FileReadTool()

def create_pm(llm_model):
    return Agent(
        role='Project Manager',
        goal='Analyze requirements and define the project scope and architecture.',
        backstory="""You are an experienced Project Manager at NeoForge AI. 
        Your job is to take raw user requirements and translate them into a clear Product Requirements Document (PRD) 
        and a high-level System Architecture.""",
        tools=[file_writer, file_reader],
        verbose=False,
        allow_delegation=False,
        llm=llm_model
    )
