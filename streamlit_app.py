import ssl
import yfinance as yf
import pandas as pd
import numpy as np
import json
import streamlit as st


# Carica il JSON di input
def load_input_data(uploaded_file):
    return json.load(uploaded_file)


# Ottieni dati di mercato
def get_market_data(symbols):
    data = yf.download(symbols, period="1y")  # Scarica dati dell'ultimo anno
    returns = data['Close'].pct_change().dropna()
    volatility = returns.std() * np.sqrt(252)  # Volatilità annualizzata
    average_return = returns.mean() * 252  # Rendimento annualizzato
    prices = data['Close'].iloc[-1]  # Prezzi correnti
    return pd.DataFrame({
        "Volatility": volatility,
        "Average Return": average_return,
        "Price": prices
    })


# Calcolo delle ponderazioni in base al profilo di rischio
def calculate_weights(data, risk_profile):
    if risk_profile == "conservative":
        weights = 1 / data["Volatility"]  # Preferenza per bassa volatilità
    elif risk_profile == "moderate":
        weights = data["Average Return"] / data["Volatility"]  # Bilanciamento rischio/rendimento
    elif risk_profile == "aggressive":
        weights = data["Average Return"]  # Preferenza per rendimento alto
    elif risk_profile == "balanced":
        weights = (data["Average Return"] + 1 / data["Volatility"]) / 2  # Combina basso rischio e rendimento
    elif risk_profile == "growth":
        weights = data["Average Return"] * 2 - data[
            "Volatility"]  # Favorisce titoli con rendimento alto penalizzando alta volatilità
    else:
        raise ValueError(f"Profilo di rischio non riconosciuto: {risk_profile}")

    # Escludi titoli troppo volatili
    weights[data["Volatility"] > data["Volatility"].quantile(0.9)] = 0
    return weights


# Ottimizza il portafoglio in base al profilo di rischio
# Ottimizza il portafoglio in base al profilo di rischio
def optimize_portfolio(input_data, market_data):
    investment_amount = input_data['investment_amount']
    risk_profile = input_data['risk_profile']
    available_assets = input_data['available_assets']
    current_portfolio = input_data['current_portfolio']

    # Filtra titoli disponibili
    symbols = [asset['symbol'] for asset in available_assets]
    data = market_data.loc[symbols].dropna()

    # Calcola le ponderazioni
    weights = calculate_weights(data, risk_profile)
    weights /= weights.sum()  # Normalizza le ponderazioni

    # Identifica posizioni da vendere
    unsuitable_positions = []
    for position in current_portfolio:
        symbol = position["symbol"]
        if symbol not in symbols:  # Non è negli available_assets
            unsuitable_positions.append(position)
        elif symbol in market_data.index and weights[symbol] == 0:  # Non è compatibile con il profilo
            unsuitable_positions.append(position)

    # Genera operazioni di vendita
    sell_operations = []
    cash_from_sales = 0
    for position in unsuitable_positions:
        if position["symbol"] in market_data.index:
            price = market_data.at[position["symbol"], "Price"]
        else:
            try:
                price = yf.Ticker(position["symbol"]).history(period="1d")["Close"].iloc[-1]
            except Exception:
                price = 0
        investment = round(position["quantity"] * price, 2)
        cash_from_sales += investment
        sell_operations.append({
            "symbol": position["symbol"],
            "action": "sell",
            "quantity": position["quantity"],
            "investment": investment
        })

    # Calcola il cash totale disponibile per gli acquisti
    total_cash_available = investment_amount + cash_from_sales

    # Calcola le operazioni di acquisto
    operations = []
    cash_spent = 0
    for symbol in symbols:
        allocation = total_cash_available * weights[symbol]
        price = data.at[symbol, "Price"]
        quantity = int(allocation / price) if price > 0 else 0
        investment = round(quantity * price, 2)
        cash_spent += investment
        operations.append({
            "symbol": symbol,
            "action": "buy",
            "quantity": quantity,
            "investment": investment
        })

    # Calcola il cash residuo
    cash_remaining = round(total_cash_available - cash_spent, 2)

    # Genera il portafoglio finale
    final_portfolio = pd.DataFrame(current_portfolio).set_index("symbol")
    operations_df = pd.DataFrame(operations).set_index("symbol")[["quantity"]]
    final_portfolio = final_portfolio.reindex(
        final_portfolio.index.union(operations_df.index)
    )
    final_portfolio["quantity"] = final_portfolio["quantity"].fillna(0) + operations_df["quantity"].fillna(0)
    final_portfolio = final_portfolio.reset_index()
    final_portfolio = final_portfolio[final_portfolio["quantity"] > 0]  # Filtra quantità a 0 o NaN

    # Calcola statistiche
    allocation = final_portfolio.set_index("symbol")["quantity"] * market_data["Price"]
    allocation_percent = (allocation / allocation.sum() * 100).round(2)

    weighted_return = round(
        (allocation * market_data["Average Return"]).sum() / allocation.sum(), 2
    ) if allocation.sum() > 0 else None

    weighted_volatility = round(
        (allocation * market_data["Volatility"]).sum() / allocation.sum(), 2
    ) if allocation.sum() > 0 else None

    return {
        "initial_portfolio": current_portfolio,
        "sell_operations": sell_operations,
        "buy_operations": operations,
        "final_portfolio": final_portfolio.to_dict(orient="records"),
        "cash_remaining": cash_remaining,
        "statistics": {
            "total_investment": round(allocation.sum(), 2),
            "allocation_percent": allocation_percent.to_dict(),
            "expected_return": weighted_return,
            "expected_volatility": weighted_volatility
        }
    }



# Streamlit App
def main():
    st.title("Ottimizzazione Portafoglio e Proposta d'Investimento")

    # Aggiungi una sezione per spiegare i profili di rischio
    with st.expander("Informazioni sui Profili di Rischio"):
        st.write("""
        ### Profili di Rischio Supportati
        - **Conservative**: Priorità ai titoli con minore volatilità per ridurre il rischio.
        - **Moderate**: Bilanciamento tra rischio e rendimento, adatto per una strategia mista.
        - **Aggressive**: Priorità ai titoli con alto potenziale di rendimento, accettando maggiore volatilità.
        - **Balanced**: Una combinazione equilibrata tra rendimento e rischio minimo.
        - **Growth**: Strategia orientata alla crescita, favorendo titoli con rendimento elevato penalizzando alta volatilità.
        """)

    # Carica il file JSON di input
    uploaded_file = st.file_uploader("Carica il file JSON di input", type="json")
    if uploaded_file:
        # Carica i dati JSON
        input_data = load_input_data(uploaded_file)

        # Scarica dati di mercato
        symbols = [asset['symbol'] for asset in input_data['available_assets']]
        st.write("Scaricamento dati di mercato...")
        market_data = get_market_data(symbols)

        # Ottimizza il portafoglio
        st.write("Ottimizzazione del portafoglio...")
        proposal = optimize_portfolio(input_data, market_data)

        # Mostra il JSON finale
        st.write("### Risultati Finali")
        st.json(proposal)


if __name__ == "__main__":
    main()
