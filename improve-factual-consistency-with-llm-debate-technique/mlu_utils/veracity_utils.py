import re
import random
import numpy as np
from collections import Counter
import json, os, shutil
import logging
import boto3, re
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import BedrockChat
from langchain_core.messages import HumanMessage
from IPython.display import display, HTML
import pandas as pd
import xml.etree.cElementTree as ET
import pickle

from prompts import *
from botocore.exceptions import ClientError

logging.basicConfig(filename='log_files/notebook_run_logs.log', encoding='utf-8', level=logging.INFO)

logger = logging.getLogger(__name__)


from langchain.llms.bedrock import Bedrock
from langchain.prompts import PromptTemplate

from IPython.display import Markdown, display

TRANSCRIPT_FOLDER = "transcripts"
DEBATE_WORD_LIMIT = 150
CONSULTANCY_WORD_LIMIT = 300
mixtral_debater_name = "expert_debater_mixtral_8_7B"
claude_debater_name = "expert_debater_sonnet_v3"
CLAUDE_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
CLAUDE_35_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
MIXTRAL_MODEL_ID = "mistral.mixtral-8x7b-instruct-v0:1"
TITAN_MODEL_ID = "amazon.titan-text-express-v1"
FLIPPED_FILE_SUFFIX = "_flipped_"
MISTRAL_7B_INSTRUCT_MODEL_ID = "mistral.mistral-7b-instruct-v0:2"
#"amazon.titan-text-express-v1"
#"amazon.titan-text-lite-v1" # 4k tokens
results_file_path = 'results/all_results.pkl'

# bedrock_runtime client. Pass internal endpoint_url here to use the internal endpoint
session = boto3.session.Session()
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name=session.region_name,
)
bedrock_runtime_client = boto3.client("bedrock-runtime")


def clear_file_contents(filename):
    print(f"clear_file_contents dir :: {dir}")
    open(filename, 'w').close()


def delete_file(filename):
    # cleanup trace files to avoid issues
    try:
        os.remove(filename)
    except OSError:
        pass


def clean_up_files_in_dir(dir):
    # cleanup trace files to avoid issues
    if os.path.isdir(dir):
        shutil.rmtree(dir)
    os.mkdir(dir)


def get_current_consultancy_transcript(debate_id):
    transcript_text = None
    transcript_filename = f"{os.getcwd()}/{TRANSCRIPT_FOLDER}/full_transcript_consultancy_" + str(debate_id) + ".log"

    try:
        with open(transcript_filename, "r") as transcript_fp:
            transcript_text = transcript_fp.readlines()
    except:
        logger.info(f"No consultancy transcript file yet :: {transcript_filename}")

    #logger.info(f"DEBUG :: transcript_text = {transcript_text}")
    return transcript_filename, transcript_text


def get_current_debate_transcript(debate_id):
    transcript_text = None
    transcript_filename = f"{os.getcwd()}/{TRANSCRIPT_FOLDER}/full_transcript_debate_" + str(debate_id) + ".log"
    try:
        with open(transcript_filename, "r") as transcript_fp:
            transcript_text = transcript_fp.readlines()
    except:
        logger.info(f"No debate transcript file yet :: {transcript_filename}")

    #logger.info(f"DEBUG :: transcript_text = {transcript_text}")
    return transcript_filename, transcript_text


def update_transcript_with_debater_response(debate_id, debater_name, round_number, debater_response):
    with open(f"{TRANSCRIPT_FOLDER}/full_transcript_debate_" + str(debate_id) + ".log", "a") as transcript_fp:
        transcript_fp.writelines(f"Debater {debater_name} argument for round {round_number + 1}")
        #is \n\n\n<ARGUMENT>")
        transcript_fp.writelines(debater_response)
        #transcript_fp.writelines(f"</ARGUMENT> \n")


def update_transcript_with_consultancy_response(debate_id, debater_name, round_number, consultancy_response):
    with open(f"{TRANSCRIPT_FOLDER}/full_transcript_consultancy_" + str(debate_id) + ".log", "a") as transcript_fp:
        transcript_fp.writelines(f" Consultant {debater_name} argument for round {round_number + 1}")
                                 # is \n\n\n<ARGUMENT>")
        transcript_fp.writelines(consultancy_response)
        #transcript_fp.writelines(f"</ARGUMENT> \n")

        
def get_argument_contents(response):
    argument_text = None
    try:
        response = response.replace("\n", "")
        search_result = re.search('<argument>.*', response)
        if search_result is not None:
            argument_text = search_result.group(0)
        #re.search('<argument>.*</argument>', response).group(0)
        logger.info(f"<argument>{argument_text}</argument>")

    except Exception as issue:
        print(issue)
        logger.info(f"response with ISSUE :: {response}") 
        print(f"response with ISSUE :: {response}")
        argument_text = re.search('<argument>.*', response).group(0)
        argument_text = argument_text + '</argument>'
        print(f">>>> Fixed argument_text :: {argument_text}")
        logger.info(f">>>> Fixed argument_text :: {argument_text}")
        
    return argument_text

def get_debate_expert_argument_request(round_number):
    if round_number == 1:
        return debate_expert_opening_argument_request
    else:
        return debate_expert_nth_argument_request


def get_debate_expert_thinking_advice(round_number):
    if round_number == 1:
        return debate_expert_thinking_advice_round_1
    elif round_number == 2:
        return debate_expert_thinking_advice_round_2
    else:
        return debate_expert_thinking_advice_round_3


def get_consultancy_expert_argument_request(round_number):
    if round_number == 1:
        return consultancy_expert_opening_argument_request
    else:
        return consultancy_expert_nth_argument_request
    

def get_consultancy_expert_thinking_advice(round_number):
    if round_number == 1:
        return consultancy_expert_thinking_advice_round_1
    else:
        return consultancy_expert_thinking_advice_round_n

    
    
def invoke_claude_v3_standalone_expert(debate_id,
                                        question,
                                        answer_a,
                                        answer_b,
                                        complete_interview
    ):
    logger.info(f"invoke_claude_v3_standalone_expert for debate_id {debate_id} >>>> ")
    MODEL_ID=CLAUDE_MODEL_ID
    #MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

    claude_model_kwargs =  {
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_k": 250,
        "top_p": 1,
        "stop_sequences": ["\n\nHuman"],
    }
    # get the debate and round number based inputs
    debater_name=claude_debater_name
    
    llm = BedrockChat(client=bedrock_runtime_client, model_id=MODEL_ID, model_kwargs=claude_model_kwargs)
    

    logger.info(f"============ START invoke_claude_v3_standalone_expert debate = {debate_id}============ ")
    
    messages = [HumanMessage(content=standalone_expert_claude_v3.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        complete_interview=complete_interview,
    ))]
    
    response = llm(messages)
    # logger.info(f"raw response ==> {response}")

    if str(type(response)) == "<class 'langchain_core.messages.ai.AIMessage'>":
            response = response.content
            response = response.strip()
            logger.info(f"Full response for update_transcript_with_consultancy_response ==> {response}")

    return response



def invoke_claude_v3(debate_id,
                     question,
                     round_number,
                     summary_defending, 
                     summary_opposing, 
                     complete_interview,
                     debate=True
                     ):
    logger.info(f"invoke_claude_v3 for debate_id {debate_id} >>>> ")
    
    MODEL_ID=CLAUDE_MODEL_ID
    #MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

    claude_model_kwargs =  {
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_k": 250,
        "top_p": 1,
        "stop_sequences": ["\n\nHuman"],
    }
    # get the debate and round number based inputs
    debater_name=claude_debater_name
    
    llm = BedrockChat(client=bedrock_runtime_client, model_id=MODEL_ID, model_kwargs=claude_model_kwargs)
    
    if debate:
        logger.info(f"============ START Claude as Debator debate = {debate} ============ ")
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id)
        nth_argument_request = get_debate_expert_argument_request(round_number)
        nth_thinking_advice = get_debate_expert_thinking_advice(round_number)
    
        messages = [HumanMessage(content=debate_claude_expert_template.format(
            expert_name=debater_name, 
            word_limit=DEBATE_WORD_LIMIT,
            question=question,
            summary_defending=summary_defending,
            summary_opposing=summary_opposing,
            complete_interview=complete_interview,
            nth_argument_request=nth_argument_request,
            nth_thinking_advice=nth_thinking_advice,
            current_debate_transcript=current_debate_transcript
        ))]
    # consultancy
    else:
        logger.info(f"============ START Claude as Consultant debate = {debate}============ ")
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id)
        nth_argument_request = get_consultancy_expert_argument_request(round_number)
        nth_thinking_advice = get_consultancy_expert_thinking_advice(round_number)
    
        messages = [HumanMessage(content=consultancy_claude_expert_template.format(
            expert_name=debater_name, 
            word_limit=CONSULTANCY_WORD_LIMIT,
            question=question,
            summary_defending=summary_defending,
            summary_opposing=summary_opposing,
            complete_interview=complete_interview,
            nth_argument_request=nth_argument_request,
            nth_thinking_advice=nth_thinking_advice,
            current_consultancy_transcript=current_consultancy_transcript
        ))]
    
    response = llm(messages)
    # logger.info(f"raw response ==> {response}")

    if str(type(response)) == "<class 'langchain_core.messages.ai.AIMessage'>":
            response = response.content
            response = response.strip()
            logger.info(f"Full response invoke_claude_v3 with <thinking> and <argument> tags ==> {response}")
            argument_only = get_argument_contents(response)
            if debate:
                update_transcript_with_debater_response(debate_id, debater_name, round_number, argument_only)
            else:
                update_transcript_with_consultancy_response(debate_id, debater_name, round_number, argument_only)

    return response



def invoke_claude_judge_consultant(debate_id,
                                       question,
                                       answer_a, 
                                       answer_b,
                                    flipped=False):

    logger.info("invoke_claude_judge_consultant >>>> ")
    transcript_filename = None
    current_consultancy_transcript = None
    if not flipped:
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id)
    else:
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id + FLIPPED_FILE_SUFFIX)
    MODEL_ID = CLAUDE_MODEL_ID
    
    logger.info(f"invoke_claude_judge_consultant :: transcript_filename >>>> {transcript_filename}")
    print(f"invoke_claude_judge_consultant :: transcript_filename >>>> {transcript_filename}")
    
    claude_prompt=consultancy_claude_judge_template.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        current_consultancy_transcript=current_consultancy_transcript
    )
    logger.info(claude_prompt)
    
    messages = [HumanMessage(content=claude_prompt)]
    
    claude_model_kwargs =  {
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_k": 250,
        "top_p": 1,
        "stop_sequences": ["\n\nHuman"],
    }

    llm = BedrockChat(client=bedrock_runtime_client, model_id=MODEL_ID, model_kwargs=claude_model_kwargs)
    
    response = llm(messages)
    # logger.info(f"raw response ==> {response}")

    if str(type(response)) == "<class 'langchain_core.messages.ai.AIMessage'>":
            response = response.content
            response = response.strip()
            logger.info(f"Full response invoke_claude_judge_consultant with <thinking> and <argument> tags ==> {response}")
            
    return response


def invoke_claude_judge_debate(debate_id,
                              question,
                       answer_a, 
                       answer_b,
                              flipped=False):
    
    logger.info("invoke_claude_judge_debate >>>> ")
    current_debate_transcript = None
    transcript_filename = None
    if not flipped:
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id)
    else:
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id + FLIPPED_FILE_SUFFIX)
    MODEL_ID = CLAUDE_MODEL_ID
    
    logger.info(f"invoke_claude_judge_debate :: transcript_filename >>>> {transcript_filename}")
    print(f"invoke_claude_judge_debate :: transcript_filename >>>> {transcript_filename}")
    
    claude_prompt=claude_debate_judge_template.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        debater_a=claude_debater_name,
        debater_b=mixtral_debater_name,
        current_debate_transcript=current_debate_transcript
    )
    logger.info(claude_prompt)
    messages = [HumanMessage(content=claude_prompt)]

    claude_model_kwargs =  {
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_k": 250,
        "top_p": 1,
        "stop_sequences": ["\n\nHuman"],
    }
    
    llm = BedrockChat(client=bedrock_runtime_client, model_id=MODEL_ID, model_kwargs=claude_model_kwargs)
    
    response = llm(messages)
    # logger.info(f"raw response ==> {response}")

    if str(type(response)) == "<class 'langchain_core.messages.ai.AIMessage'>":
            response = response.content
            response = response.strip()

    return response


def generate_text_mistral(model_id, body):
    """
    Generate text using a Mistral AI model.
    Args:
        model_id (str): The model ID to use.
        body (str) : The request body to use.
    Returns:
        JSON: The response from the model.
    """

    #logger.info("Generating text with Mistral AI model %s", model_id)

    bedrock = boto3.client(service_name='bedrock-runtime')

    response = bedrock.invoke_model(
        body=body,
        modelId=model_id
    )

    #logger.info("Successfully generated text with Mistral AI model %s", model_id)
    
    return response


def invoke_mistral(debate_id, 
                     round_number,
                     question,
                     summary_defending, 
                     summary_opposing, 
                     complete_interview, 
                     ):
    logger.info(f"invoke_mistral for debate_id {debate_id} >>>> ")
    # get the debate and round number based inputs
    MODEL_ID = MIXTRAL_MODEL_ID
    #MODEL_ID = "mistral.mistral-7b-instruct-v0:2"

    debater_name=mixtral_debater_name
    transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id)
    nth_argument_request = get_debate_expert_argument_request(round_number)
    nth_thinking_advice = get_debate_expert_thinking_advice(round_number)
   
    logger.info(f"============ START Mistral as Debator  ============ ")
    mixtral_prompt=debate_mistral_expert_template.format(
        expert_name=debater_name, 
        word_limit=DEBATE_WORD_LIMIT,
        question=question,
        summary_defending=summary_defending,
        summary_opposing=summary_opposing,
        complete_interview=complete_interview,
        nth_argument_request=nth_argument_request,
        nth_thinking_advice=nth_thinking_advice,
        current_debate_transcript=current_debate_transcript
    )
    logger.info(mixtral_prompt)
    logger.info(f"============ END Mistral as Debator  ============ ")

    
    body = json.dumps({
        "prompt": mixtral_prompt,
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 5
    })

    response = generate_text_mistral(model_id=MODEL_ID, body=body)

    response_body = json.loads(response.get('body').read())

    outputs = response_body.get('outputs')
    logger.info(f"Full response invoke_mistral with <thinking> and <argument> tags ==> {outputs[0]['text']}")
    full_response = outputs[0]['text']
    argument_only = get_argument_contents(full_response)
    update_transcript_with_debater_response(debate_id, debater_name, round_number, argument_only)
    return outputs[0]['text']


def generate_text_titan(model_id, 
                        body):
    """
    Generate text using Amazon Titan Text models on demand.
    Args:
        model_id (str): The model ID to use.
        body (str) : The request body to use.
    Returns:
        response (json): The response from the model.
    """

    #logger.info("Generating text with Amazon Titan Text model %s", model_id)

    bedrock = boto3.client(service_name='bedrock-runtime')

    accept = "application/json"
    content_type = "application/json"

    response = bedrock.invoke_model(
        body=body, modelId=model_id, accept=accept, contentType=content_type
    )
    response_body = json.loads(response.get("body").read())

    finish_reason = response_body.get("error")

    if finish_reason is not None:
        raise ImageError(f"Text generation error. Error is {finish_reason}")

    #logger.info("Successfully generated text with Amazon Titan Text model %s", model_id)

    return response_body

def invoke_titan_judge_debate(debate_id,
                              question,
                       answer_a, 
                       answer_b,
                              flipped=False):
    
    logger.info("invoke_titan_judge_debate >>>> ")
    current_debate_transcript = None
    transcript_filename = None
    if not flipped:
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id)
    else:
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id + FLIPPED_FILE_SUFFIX)
    MODEL_ID = TITAN_MODEL_ID
    
    logger.info(f"invoke_titan_judge_debate :: transcript_filename >>>> {transcript_filename}")
    print(f"invoke_titan_judge_debate :: transcript_filename >>>> {transcript_filename}")
    
    titan_prompt=debate_expert_judge_template.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        debater_a=claude_debater_name,
        debater_b=mixtral_debater_name,
        current_debate_transcript=current_debate_transcript
    )
    logger.info(titan_prompt)

    body = json.dumps({
            "inputText": titan_prompt,
            "textGenerationConfig": {
                "maxTokenCount": 4000,
                "stopSequences": [],
                "temperature": 0.0,
                "topP": 1.0
            }
        })
    
    response_body = generate_text_titan(MODEL_ID, body)
    
    # if titan used as debater
    # update_transcript_with_debater_response(debate_id, debater_name, round_number, response_body['results'][0]['outputText'])
    
    return response_body['results'][0]['outputText']



def invoke_mistral_judge_debate(debate_id,
                              question,
                       answer_a, 
                       answer_b,
                              flipped=False):
    
    logger.info("invoke_mistral_judge_debate >>>> ")
    current_debate_transcript = None
    transcript_filename = None
    if not flipped:
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id)
    else:
        transcript_filename, current_debate_transcript = get_current_debate_transcript(debate_id + FLIPPED_FILE_SUFFIX)
    MODEL_ID = MISTRAL_7B_INSTRUCT_MODEL_ID
    
    logger.info(f"invoke_mistral_judge_debate :: transcript_filename >>>> {transcript_filename}")
    print(f"invoke_mistral_judge_debate :: transcript_filename >>>> {transcript_filename}")
    
    mistral_prompt=mistral_debate_naive_judge_template.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        debater_a=claude_debater_name,
        debater_b=mixtral_debater_name,
        current_debate_transcript=current_debate_transcript
    )
    logger.info(mistral_prompt)

    body = json.dumps({
        "prompt": mistral_prompt,
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 5
    })

    response = generate_text_mistral(model_id=MODEL_ID, body=body)

    response_body = json.loads(response.get('body').read())

    outputs = response_body.get('outputs')
    logger.info(f"Full response invoke_mistral_judge_debate  ==> {outputs[0]['text']}")
    full_response = outputs[0]['text']
    return outputs[0]['text']


def invoke_titan_judge_consultant(debate_id,
                              question,
                       answer_a, 
                       answer_b,
                                 flipped=False):
    
    logger.info("invoke_titan_judge_consultant >>>> ")
    transcript_filename = None
    current_consultancy_transcript = None
    if not flipped:
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id)
    else:
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id + FLIPPED_FILE_SUFFIX)
    MODEL_ID = TITAN_MODEL_ID
    
    logger.info(f"invoke_titan_judge_consultant :: transcript_filename >>>> {transcript_filename}")
    print(f"invoke_titan_judge_consultant :: transcript_filename >>>> {transcript_filename}")
    
    titan_prompt=consultancy_titan_judge_template.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        current_consultancy_transcript=current_consultancy_transcript
    )
    logger.info(titan_prompt)

    body = json.dumps({
            "inputText": titan_prompt,
            "textGenerationConfig": {
                "maxTokenCount": 4000,
                "stopSequences": [],
                "temperature": 0.0,
                "topP": 1.0
            }
        })
    
    response_body = generate_text_titan(MODEL_ID, body)
    
    # if titan used as debater
    # update_transcript_with_debater_response(debate_id, debater_name, round_number, response_body['results'][0]['outputText'])
    
    return response_body['results'][0]['outputText']




def invoke_mistral_judge_consultant(debate_id,
                                       question,
                                       answer_a, 
                                       answer_b,
                                    flipped=False):
    
    logger.info("invoke_mistral_judge_consultant >>>> ")
    transcript_filename = None
    current_consultancy_transcript = None
    if not flipped:
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id)
    else:
        transcript_filename, current_consultancy_transcript = get_current_consultancy_transcript(debate_id + FLIPPED_FILE_SUFFIX)
    MODEL_ID = MISTRAL_7B_INSTRUCT_MODEL_ID
    
    logger.info(f"invoke_mistral_judge_consultant :: transcript_filename >>>> {transcript_filename}")
    print(f"invoke_mistral_judge_consultant :: transcript_filename >>>> {transcript_filename}")
    
    mistral_prompt=consultancy_mistral_judge_template.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        current_consultancy_transcript=current_consultancy_transcript
    )
    logger.info(mistral_prompt)
    
    body = json.dumps({
        "prompt": mistral_prompt,
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 5
    })

    response = generate_text_mistral(model_id=MODEL_ID, body=body)

    response_body = json.loads(response.get('body').read())

    outputs = response_body.get('outputs')
    logger.info(f"Full response invoke_mistral with <thinking> and <argument> tags ==> {outputs[0]['text']}")
    full_response = outputs[0]['text']

    return outputs[0]['text']


def invoke_titan_judge_standalone_naive(debate_id,
    question,
    answer_a,
    answer_b):
    
    logger.info("invoke_titan_judge_standalone_naive >>>> ")
    MODEL_ID = TITAN_MODEL_ID
    
    titan_prompt=standalone_naive_titan_judge_prompt.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b
    )
    logger.info(titan_prompt)

    body = json.dumps({
            "inputText": titan_prompt,
            "textGenerationConfig": {
                "maxTokenCount": 4000,
                "stopSequences": [],
                "temperature": 0.0,
                "topP": 1.0
            }
        })
    response_body = generate_text_titan(MODEL_ID, body)
    return response_body['results'][0]['outputText']


def invoke_titan_judge_standalone_expert(debate_id,
                                         question,
                                         answer_a,
                                         answer_b,
                                         complete_interview):
    
    MODEL_ID = TITAN_MODEL_ID
    logger.info("invoke_titan_judge_standalone_expert >>>> ")
    
    titan_prompt=standalone_expert_titan_judge_prompt.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        complete_interview=complete_interview,
    )
    logger.info(titan_prompt)

    body = json.dumps({
            "inputText": titan_prompt,
            "textGenerationConfig": {
                "maxTokenCount": 4000,
                "stopSequences": [],
                "temperature": 0.0,
                "topP": 1.0
            }
        })
    response_body = generate_text_titan(MODEL_ID, body)
    return response_body['results'][0]['outputText']



    
def invoke_titan(prompt:str,
                 debate_id:str, debater_name:str, round_number:str, 
                 model:str="amazon.titan-text-lite-v1", 
                 temperature:float=0.0, 
                 max_tokens:int=4000, 
                 stop_sequences:list=[], 
                 n:int=1):
    
    logger.info("invoke_titan >>>> ")
    body = json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": max_tokens,
                "stopSequences": stop_sequences,
                "temperature": temperature,
                "topP": 1.0
            }
        })

    response_body = generate_text_titan(model, body)

    # if titan used as debater
    # update_transcript_with_debater_response(debate_id, debater_name, round_number, response_body['results'][0]['outputText'])
    return response_body['results'][0]['outputText']


def pretty_print(df):
    return display(HTML( df.to_html().replace("\\n","<br>"))) # .replace("\\n","<p>") 


def highlight_cols(s):
    color = 'grey'
    return 'background-color: %s' % color


def format_final_response(debate_id, round_num, question, answer_a, answer_b, judge_response):
    question = question.replace('$', r'\$')
    answer_a = answer_a.replace('$', r'\$')
    answer_b = answer_b.replace('$', r'\$')
    judge_response = judge_response.replace('$', r'\$')
    final_answer_list = [judge_response]
    round_num_list = [str(round_num)]
    debate_id_list = [str(debate_id)]
    question_list = [question + "\n Answer A:" + answer_a + "\n Answer B:" + answer_b]

    # Store and print as a dataframe
    response_df = pd.DataFrame(list(zip(debate_id_list, round_num_list, question_list,  final_answer_list )), 
                                  columns=["Debate ID", "Round #", "Task Question", "Judge Response"])
    response_df.style.set_properties(**{'text-align': 'left', 'border': '1px solid black'})
    response_df.to_string(justify='left', index=False)
    with pd.option_context("display.max_colwidth", None):
        pretty_print(response_df)

    
def final_accuracy_comparison_judge(accuracy_naive_judge, accuracy_expert_judge):
    
    accuracy_naive_judge_list = [accuracy_naive_judge]
    accuracy_expert_judge_list = [accuracy_expert_judge]
    
    # Store and print as a dataframe
    response_df = pd.DataFrame(list(zip(accuracy_naive_judge_list, accuracy_expert_judge_list )), 
                                  columns=["Naive Judge", "Expert Judge"])
    response_df.style.set_properties(**{'text-align': 'left', 'border': '1px solid black'})
    response_df.to_string(justify='left', index=False)
    
    with pd.option_context("display.max_colwidth", None):
        pretty_print(response_df)

def final_accuracy_comparison_judge_and_consultant(accuracy_naive_judge, accuracy_expert_judge, accuracy_consultant_judge):
    
    accuracy_naive_judge_list = [accuracy_naive_judge]
    accuracy_expert_judge_list = [accuracy_expert_judge]
    accuracy_consultant_judge_list = [accuracy_consultant_judge]
    
    # Store and print as a dataframe
    response_df = pd.DataFrame(list(zip(accuracy_naive_judge_list, accuracy_expert_judge_list, accuracy_consultant_judge_list )), 
                                  columns=["Naive Judge", "Expert Judge", "LLM Consultancy"])
    response_df.style.set_properties(**{'text-align': 'left', 'border': '1px solid black'})
    response_df.to_string(justify='left', index=False)
    
    with pd.option_context("display.max_colwidth", None):
        pretty_print(response_df)

def final_accuracy_comparison(accuracy_naive_judge, accuracy_expert_judge, accuracy_consultant_judge, accuracy_debate_judge):
    
    accuracy_naive_judge_list = [accuracy_naive_judge]
    accuracy_expert_judge_list = [accuracy_expert_judge]
    accuracy_consultant_judge_list = [accuracy_consultant_judge]
    accuracy_debate_judge_list = [accuracy_debate_judge]
    
    # Store and print as a dataframe
    response_df = pd.DataFrame(list(zip(accuracy_naive_judge_list, accuracy_expert_judge_list, accuracy_consultant_judge_list,  accuracy_debate_judge_list )), 
                                  columns=["Naive Judge", "Expert Judge", "LLM Consultancy", "LLM Debate"])
    response_df.style.set_properties(**{'text-align': 'left', 'border': '1px solid black'})
    response_df.to_string(justify='left', index=False)
    response_df.style.applymap(highlight_cols, subset=pd.IndexSlice[:, ['LLM Debate']])
    
    with pd.option_context("display.max_colwidth", None):
        pretty_print(response_df)



def extract_final_answer(judge_response, flipped=False):
    '''
    assumes Answer A is correct/True and Answer B is False/incorrect
    '''
    judge_response = judge_response.lower()
    a_pos = (judge_response.find('final answer: a') != -1 or judge_response.find('final answer a') != -1 or judge_response.find('final answer: <a>'))
    b_pos = (judge_response.find('final answer: b') != -1 or judge_response.find('final answer b') != -1 or judge_response.find('final answer: <b>'))
    if a_pos >= 0:
        if not flipped:
            return True
        else:
            return False
    elif b_pos>= 0:
        if not flipped:
            return False
        else:
            return True
    else:# none found - no text "final answer found"
        print(f"entering None scenario for final answer")
        a_pos = (judge_response.find('final answer: a') != -1 or judge_response.find('final answer a') != -1 or judge_response.find('final answer: <a>'))
        b_pos = (judge_response.find('final answer: b') != -1 or judge_response.find('final answer b') != -1 or judge_response.find('final answer: <b>'))
        if a_pos >= 0:
            if not flipped:
                return True
            else:
                return False
        elif b_pos>= 0:
            if not flipped:
                return False
            else:
                return True
        
    return None


def find_num_matching_elements(list1, list2):
    match_count = 0
    for element1, element2 in zip(list1, list2):
        if element1 == element2 and element1 is not None and element2 is not None:
            match_count +=1
    
    return match_count


def get_win_rate_per_model(regular_list, flipped_list):
    
    # regular Mistral = True, Claude = False
    most_common_regular_value , regular_count = Counter(regular_list).most_common()[0]
    print(f"most_common_regular_value ={most_common_regular_value} , regular_count = {regular_count}")
    if most_common_regular_value or most_common_regular_value == True:
        mistral_regular_win_rate = regular_count/10
        claude_regular_win_rate = 1 - mistral_regular_win_rate
    elif not most_common_regular_value or most_common_regular_value == False:
        claude_regular_win_rate = regular_count/10
        mistral_regular_win_rate = 1 - claude_regular_win_rate
    
    
    # flipped Claude = True, Mistral = False
    most_common_flipped_value, flipped_count = Counter(flipped_list).most_common()[0]
    print(f"most_common_flipped_value ={most_common_flipped_value} , flipped_count = {flipped_count}")
    if most_common_flipped_value or most_common_flipped_value == True:
        claude_flipped_win_rate = flipped_count/10
        mistral_flipped_win_rate = 1 - claude_flipped_win_rate
    elif not most_common_flipped_value or most_common_flipped_value == False:
        mistral_flipped_win_rate = flipped_count/10
        claude_flipped_win_rate = 1 - mistral_flipped_win_rate
        
        
    mistral_avg_win_rate = (mistral_regular_win_rate + mistral_flipped_win_rate)/2.0
    claude_avg_win_rate = (claude_regular_win_rate + claude_flipped_win_rate)/2.0
    
    logger.info(f"""claude_regular_win_rate :: {claude_regular_win_rate} 
                mistral_regular_win_rate :: {mistral_regular_win_rate} 
                claude_flipped_win_rate :: {claude_flipped_win_rate}
                mistral_flipped_win_rate :: {mistral_flipped_win_rate} """)
    
    print(f"""\n claude_regular_win_rate :: {claude_regular_win_rate} 
                \n mistral_regular_win_rate :: {mistral_regular_win_rate} 
                \n claude_flipped_win_rate :: {claude_flipped_win_rate}
                \n mistral_flipped_win_rate :: {mistral_flipped_win_rate} """)
    
    return claude_avg_win_rate, mistral_avg_win_rate


def win_rate_comparison(claude_avg_win_rate, mistral_avg_win_rate):
    
    claude_avg_win_rate_list = [claude_avg_win_rate]
    mistral_avg_win_rate_list = [mistral_avg_win_rate]
    
    # Store and print as a dataframe
    response_df = pd.DataFrame(list(zip(claude_avg_win_rate_list, mistral_avg_win_rate_list)), 
                                  columns=["Claude Win Rate", "Mixtral Win Rate"])
    response_df.style.set_properties(**{'text-align': 'left', 'border': '1px solid black'})
    response_df.to_string(justify='left', index=False)
     
    with pd.option_context("display.max_colwidth", None):
        pretty_print(response_df)



def invoke_mistral_standalone_naive(debate_id,
    question,
    answer_a,
    answer_b):
    
    logger.info(f"invoke_mistral_judge_standalone_naive for debate_id {debate_id} >>>> ")
    MODEL_ID = MISTRAL_7B_INSTRUCT_MODEL_ID
    
    mistral_prompt=standalone_naive_mistral.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b
    )
    logger.info(mistral_prompt)

    body = json.dumps({
        "prompt": mistral_prompt,
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 5
    })

    response = generate_text_mistral(model_id=MODEL_ID, body=body)
    response_body = json.loads(response.get('body').read())

    outputs = response_body.get('outputs')
    logger.info(f"Full response standalone_naive_mistral ==> {outputs[0]['text']}")
    full_response = outputs[0]['text']
    return outputs[0]['text']



def invoke_mistral_standalone_expert(debate_id,
                                         question,
                                         answer_a,
                                         answer_b,
                                         complete_interview):

    MODEL_ID = MISTRAL_7B_INSTRUCT_MODEL_ID
    logger.info(f"invoke_mistral_judge_standalone_expert for debate_id {debate_id} >>>> ")

    mistral_prompt=standalone_expert_mistral.format(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        complete_interview=complete_interview,
    )
    logger.info(mistral_prompt)

    body = json.dumps({
        "prompt": mistral_prompt,
        "max_tokens": 4000,
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 5
    })

    response = generate_text_mistral(model_id=MODEL_ID, body=body)
    response_body = json.loads(response.get('body').read())

    outputs = response_body.get('outputs')
    logger.info(f"Full response standalone_naive_mistral ==> {outputs[0]['text']}")
    full_response = outputs[0]['text']
    return outputs[0]['text']


def init_results_file():
    clean_up_files_in_dir('results')
    dictionary = {}
    with open(results_file_path, 'wb') as f:
        pickle.dump(dictionary, f)
    
def get_each_experiment_result(experiment_name):
    with open(results_file_path, 'r+b') as f:
        loaded_dict = pickle.load(f)
        print(loaded_dict)
        return loaded_dict[experiment_name]
        
    
def save_each_experiment_result(results_dict):
    loaded_dict = None
    with open(results_file_path, 'r+b') as fr:
        loaded_dict = pickle.load(fr)
        loaded_dict.update(results_dict)

    print(loaded_dict)

    with open(results_file_path, 'w+b') as fw:
        pickle.dump(loaded_dict, fw)
