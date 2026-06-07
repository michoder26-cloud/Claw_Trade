import json
from pathlib import Path

def generate_report_markdown(json_path, output_name, out_file):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    monthly_reports = data["monthly_reports"]
    
    markdown_lines = []
    markdown_lines.append(f"### {output_name}")
    markdown_lines.append("")
    markdown_lines.append("| เดือน | ทุนเริ่มต้น (USD) | ทุนเริ่มต้น (Cent) | กำไรสุทธิเดือนนี้ (USD) | กำไรสะสม (USD) | Return เดือนนี้ | Win Rate | จำนวนไม้ (W/L) | Max DD |")
    markdown_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    prev_balance = 10000.0
    total_trades = 0
    total_wins = 0
    total_losses = 0
    
    for report in monthly_reports:
        month = report["month"]
        net_profit_cumulative = report["net_profit"]
        
        ending_balance = 10000.0 + net_profit_cumulative
        starting_balance = prev_balance
        
        monthly_profit = ending_balance - starting_balance
        monthly_return_pct = (monthly_profit / starting_balance) * 100 if starting_balance > 0 else 0
        
        starting_balance_cents = starting_balance * 100
        monthly_profit_usd = monthly_profit
        net_profit_cumulative_usd = net_profit_cumulative
        
        win_rate = report["win_rate"]
        t_trades = report["total_trades"]
        w_trades = report["winning_trades"]
        l_trades = report["losing_trades"]
        max_dd = report["max_drawdown_pct"]
        
        total_trades += t_trades
        total_wins += w_trades
        total_losses += l_trades
        prev_balance = ending_balance
        
        month_formatted = f"**{month}**"
        
        markdown_lines.append(
            f"| {month_formatted} | ${starting_balance:,.2f} | {starting_balance_cents:,.0f} | "
            f"{'+' if monthly_profit_usd >= 0 else ''}${monthly_profit_usd:,.2f} | "
            f"${net_profit_cumulative_usd:,.2f} | "
            f"{'+' if monthly_return_pct >= 0 else ''}{monthly_return_pct:.2f}% | "
            f"{win_rate:.1f}% | {t_trades} ({w_trades}/{l_trades}) | {max_dd:.2f}% |"
        )
        
    markdown_lines.append("")
    markdown_lines.append(f"**ยอดเงินปลายทาง:** ${prev_balance:,.2f} ({prev_balance*100:,.0f} Cents)")
    markdown_lines.append(f"**กำไรสะสมทั้งหมด:** ${prev_balance - 10000.0:,.2f} ({(prev_balance - 10000.0)/10000.0*100:.2f}%)")
    wr_total = (total_wins / total_trades * 100) if total_trades > 0 else 0
    markdown_lines.append(f"**จำนวนการเข้าออเดอร์ทั้งหมด:** {total_trades} ไม้ (ชนะ {total_wins} / แพ้ {total_losses} | Win Rate {wr_total:.1f}%)")
    markdown_lines.append("\n" + "="*50 + "\n")
    
    out_file.write("\n".join(markdown_lines) + "\n")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.resolve()
    
    report_md_path = project_root / "scratch" / "report_output.md"
    with open(report_md_path, "w", encoding="utf-8") as out_file:
        out_file.write("# ผลการวิเคราะห์ Backtest แบบละเอียด (หลังแก้บั๊กแล้ว)\n\n")
        
        # Analyze 12-month
        json12 = project_root / "scratch" / "multi_month_training_results_safe.json"
        if json12.exists():
            generate_report_markdown(json12, "12-Month Safe Backtest (June 2025 - May 2026)", out_file)
            
        # Analyze 24-month
        json24 = project_root / "scratch" / "24month_training_results.json"
        if json24.exists():
            generate_report_markdown(json24, "24-Month Continuous Backtest (June 2024 - May 2026)", out_file)
            
    print(f"✅ Report successfully generated at {report_md_path}")
