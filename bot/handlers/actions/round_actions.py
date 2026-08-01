from bot.handlers.actions.tournament_actions import next_pair
from bot.services.round_service import apply_result, apply_result_team
from bot.ui.views import show_standings, show_score_buttons


async def set_score(chat_id, data, context):
    score = int(data.split("_")[-1])
    await finish_round_action(chat_id, context, score)


async def set_draw(chat_id, context):
    await finish_round_action(chat_id, context)


async def finish_round_action(chat_id, context, score=None):
    await apply_result(chat_id, context, score)

    await show_standings(chat_id, context)
    await next_pair(chat_id, context)


async def result_team(chat_id, data, context):
    winner_team = await apply_result_team(chat_id, context, data)

    await show_score_buttons(chat_id, context, winner_team)
