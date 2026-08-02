from bot.state import pending_edit_selection, pending_management, pending_manual_pair, pending_scores


def clear_management_state(chat_id):
    pending_management.pop(chat_id, None)
    pending_manual_pair.pop(chat_id, None)
    pending_edit_selection.pop(chat_id, None)

def clear_active_round_state(chat_id):
    pending_scores.pop(chat_id, None)
