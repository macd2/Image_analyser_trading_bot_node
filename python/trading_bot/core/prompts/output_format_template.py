## OUTPUT REQUIREMENTS
output_prompt = f"""
    ## OUTPUT RULES
    Return your analysis in this exact JSON format:
    {{
        "recommendation": "buy" | "hold" | "sell",
        "summary": "Brief analysis summary (max 50 words)",
        "key_levels": {{
            "support": 0.0,
            "resistance": 0.0
        }},
        "risk_factors": ["Risk factor 1", "Risk factor 2"],
        "market_condition": "TRENDING" | "RANGING",
        "market_direction": "UP" | "DOWN" | "SIDEWAYS",
        "evidence": "Specific evidence supporting recommendation",
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "direction": "Long" | "Short",
        "entry_explanation": "Why this entry price?",
        "take_profit_explanation": "Why this take profit?",
        "stop_loss_explanation": "Why this stop loss?",
        "confidence": 0.0,
        "risk_reward_ratio": 0.0,
        "rationale": "Brief rationale for recommendation (MUST be always provided)"
    }}
    """