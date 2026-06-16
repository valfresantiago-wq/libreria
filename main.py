from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
import mercadopago
import os
import tempfile
from PyPDF2 import PdfReader
import uvicorn
import hashlib
from datetime import datetime

app = FastAPI()

# ============================================
# 🔥 CONFIGURACIÓN - ¡CAMBIÁ ESTOS DATOS!
# ============================================
# ⚠️ REEMPLAZÁ con tu Access Token de PRODUCCIÓN (APP_USR-...)
MERCADO_PAGO_ACCESS_TOKEN = "APP_USR-8558854920386159-061311-9a6a6e657305b58b3e742c758c2d0635-1643983985"

# ⚠️ REEMPLAZÁ con tu URL de Render (cuando la tengas)
PUBLIC_URL = "https://TU_APP_EN_RENDER.onrender.com"  # <--- CAMBIÁ ESTO

sdk = mercadopago.SDK(MERCADO_PAGO_ACCESS_TOKEN)
pedidos_db = {}

# ============================================
# FUNCIÓN DE CÁLCULO DE PRECIOS
# ============================================
def calcular_precio(paginas: int, color: str, calidad: str, tamaño: str, copias: int) -> int:
    if color == "byn":
        precio = 100
    else:
        precio = 300
    
    if calidad == "alta":
        precio = int(precio * 1.4)
    elif calidad == "borrador":
        precio = int(precio * 0.7)
    
    if tamaño == "A3":
        precio = int(precio * 1.8)
    elif tamaño == "oficio":
        precio = int(precio * 1.3)
    
    total = precio * paginas * copias
    if paginas > 50:
        total = int(total * 0.9)
    return total

# ============================================
# FRONTEND (Página web que ven los clientes)
# ============================================
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Impresiones Pro</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js"></script>
        <style>
            * { box-sizing: border-box; }
            body { font-family: Arial; background: #f0f4f8; padding: 20px; display: flex; justify-content: center; }
            .container { max-width: 600px; width: 100%; background: white; padding: 30px; border-radius: 24px; box-shadow: 0 12px 40px rgba(0,0,0,0.1); }
            h1 { font-size: 28px; }
            .subtitle { color: #4a5568; border-left: 4px solid #3182ce; padding-left: 12px; }
            input, select { width: 100%; padding: 12px; border-radius: 12px; border: 2px solid #e2e8f0; }
            .file-upload-wrapper { border: 2px dashed #cbd5e0; border-radius: 16px; padding: 20px; text-align: center; cursor: pointer; background: #f7fafc; }
            button { width: 100%; background: #3182ce; color: white; font-weight: 700; padding: 16px; border: none; border-radius: 14px; margin-top: 24px; cursor: pointer; }
            #resultado { display: none; margin-top: 20px; padding: 20px; background: #f0fff4; border-radius: 16px; text-align: center; }
            .precio { font-size: 32px; font-weight: 800; color: #22543d; }
            #btnPagarMp { display: none; background: #009ee3; color: white; font-weight: 700; padding: 16px; border-radius: 14px; text-decoration: none; width: 100%; text-align: center; margin-top: 20px; border: none; font-size: 18px; cursor: pointer; }
            #btnPagarMp:hover { background: #007bb5; }
            #preview-container { margin: 16px 0; text-align: center; display: none; }
            #preview-container canvas { max-width: 100%; border-radius: 8px; }
            .error-box { display: none; background: #fed7d7; padding: 16px; border-radius: 12px; margin-top: 16px; color: #742a2a; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📄 Impresiones Pro</h1>
            <div class="subtitle">Subí tu PDF y pagá al instante</div>

            <form id="uploadForm" enctype="multipart/form-data">
                <div class="file-upload-wrapper">
                    <span id="fileText">📎 Tocá para subir tu PDF</span>
                    <input type="file" id="archivo" accept=".pdf" required>
                </div>

                <div id="preview-container">
                    <canvas id="pdf-preview-canvas"></canvas>
                </div>

                <label>🎨 Color</label>
                <select id="color">
                    <option value="byn">Blanco y Negro</option>
                    <option value="color">Color</option>
                </select>

                <label>📐 Tamaño</label>
                <select id="tamaño">
                    <option value="A4">A4</option>
                    <option value="A3">A3 (+80%)</option>
                    <option value="oficio">Oficio (+30%)</option>
                </select>

                <label>🖨️ Calidad</label>
                <select id="calidad">
                    <option value="borrador">Borrador (-30%)</option>
                    <option value="normal" selected>Normal</option>
                    <option value="alta">Alta (+40%)</option>
                </select>

                <label>📄 Copias</label>
                <input type="number" id="copias" value="1" min="1" max="20">

                <button type="submit">💰 Calcular y Pagar</button>
            </form>

            <div id="resultado">
                <div class="precio" id="precioTotal">$0</div>
                <div id="detallePedido"></div>
                <a id="btnPagarMp" href="#" target="_blank">💳 Pagar con Mercado Pago</a>
            </div>
            <div class="error-box" id="errorBox"></div>
        </div>

        <script>
            // ============================================
            // 1. VISTA PREVIA DEL PDF
            // ============================================
            const archivoInput = document.getElementById('archivo');
            archivoInput.addEventListener('change', function(e) {
                const file = e.target.files[0];
                if (file) {
                    document.getElementById('fileText').textContent = file.name;
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const typedarray = new Uint8Array(e.target.result);
                        pdfjsLib.getDocument(typedarray).promise.then(function(pdf) {
                            pdf.getPage(1).then(function(page) {
                                const canvas = document.getElementById('pdf-preview-canvas');
                                const context = canvas.getContext('2d');
                                const viewport = page.getViewport({ scale: 1.2 });
                                canvas.width = viewport.width;
                                canvas.height = viewport.height;
                                page.render({ canvasContext: context, viewport: viewport });
                                document.getElementById('preview-container').style.display = 'block';
                            });
                        });
                    };
                    reader.readAsArrayBuffer(file);
                }
            });

            // ============================================
            // 2. ENVÍO DEL FORMULARIO Y PAGO
            // ============================================
            document.getElementById('uploadForm').onsubmit = async (e) => {
                e.preventDefault();
                const archivo = document.getElementById('archivo').files[0];
                if (!archivo) return alert('Seleccioná un PDF');

                const formData = new FormData();
                formData.append('archivo', archivo);
                formData.append('color', document.getElementById('color').value);
                formData.append('tamaño', document.getElementById('tamaño').value);
                formData.append('calidad', document.getElementById('calidad').value);
                formData.append('copias', document.getElementById('copias').value);

                try {
                    const response = await fetch('/procesar', { method: 'POST', body: formData });
                    const data = await response.json();
                    
                    if (!response.ok) {
                        document.getElementById('errorBox').textContent = '❌ ' + data.error;
                        document.getElementById('errorBox').style.display = 'block';
                        return;
                    }

                    document.getElementById('precioTotal').textContent = '$' + data.total;
                    document.getElementById('detallePedido').innerHTML = `
                        📄 ${data.paginas} páginas · ${data.copias} copias · ${data.color_texto} · ${data.tamaño}
                    `;
                    
                    // Mostrar el botón de pago
                    const btnPagar = document.getElementById('btnPagarMp');
                    btnPagar.href = data.init_point;
                    btnPagar.style.display = 'block';
                    document.getElementById('resultado').style.display = 'block';

                } catch (error) {
                    document.getElementById('errorBox').textContent = '❌ Error de conexión. Intentá de nuevo.';
                    document.getElementById('errorBox').style.display = 'block';
                }
            };
        </script>
    </body>
    </html>
    """

# ============================================
# BACKEND - PROCESAR PEDIDO
# ============================================
@app.post("/procesar")
async def procesar_pedido(
    archivo: UploadFile = File(...),
    color: str = Form(...),
    tamaño: str = Form(...),
    calidad: str = Form(...),
    copias: int = Form(...)
):
    if not archivo.filename.endswith('.pdf'):
        raise HTTPException(400, {"error": "Solo PDF"})

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await archivo.read()
            tmp.write(content)
            tmp_path = tmp.name

        reader = PdfReader(tmp_path)
        paginas = len(reader.pages)

        if paginas > 200:
            os.unlink(tmp_path)
            raise HTTPException(400, {"error": f"Máximo 200 páginas. Tiene {paginas}."})

        total = calcular_precio(paginas, color, calidad, tamaño, copias)

        # ============================================
        # CREAR PREFERENCIA EN MERCADO PAGO
        # ============================================
        preference_data = {
            "items": [
                {
                    "title": f"Impresión {tamaño} - {paginas} páginas",
                    "quantity": copias,
                    "unit_price": total,
                    "currency_id": "ARS",
                }
            ],
            "payment_methods": {
                "excluded_payment_methods": [],
                "excluded_payment_types": [],  # <--- PERMITE TODOS (Dinero en cuenta, créditos, etc.)
                "installments": 12
            },
            "back_urls": {
                "success": f"{PUBLIC_URL}/success",
                "failure": f"{PUBLIC_URL}/failure",
                "pending": f"{PUBLIC_URL}/pending"
            },
            "notification_url": f"{PUBLIC_URL}/webhook/mercadopago",
            "auto_return": "approved",
            "external_reference": hashlib.md5(archivo.filename.encode()).hexdigest()
        }

        result = sdk.preference().create(preference_data)
        preference = result["response"]

        pedido_id = preference["external_reference"]
        pedidos_db[pedido_id] = {
            "file_path": tmp_path,
            "paginas": paginas,
            "copias": copias,
            "total": total,
            "pagado": False,
            "fecha": datetime.now().isoformat()
        }

        # ============================================
        # DEVOLVER LINK DE PAGO
        # ============================================
        return {
            "total": total,
            "paginas": paginas,
            "copias": copias,
            "color_texto": "Color" if color == "color" else "Blanco y Negro",
            "tamaño": tamaño,
            "preference_id": preference["id"],
            "pedido_id": pedido_id,
            "init_point": preference["init_point"]  # <--- LINK DE PAGO
        }

    except Exception as e:
        raise HTTPException(500, {"error": str(e)})

# ============================================
# WEBHOOK - CONFIRMAR PAGOS
# ============================================
@app.post("/webhook/mercadopago")
async def webhook(request: Request):
    try:
        data = await request.json()
        payment_id = data.get("data", {}).get("id")
        if not payment_id:
            return {"status": "ignored"}

        payment_response = sdk.payment().get(payment_id)
        payment = payment_response["response"]

        if payment["status"] == "approved":
            pedido_id = payment.get("external_reference")
            if pedido_id and pedido_id in pedidos_db:
                pedidos_db[pedido_id]["pagado"] = True
                print(f"✅ Pago aprobado para {pedido_id}")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error"}

# ============================================
# PÁGINAS DE REDIRECCIÓN
# ============================================
@app.get("/success")
async def success():
    return HTMLResponse("<h1>✅ Pago exitoso</h1><p>Tu pedido está en proceso.</p>")

@app.get("/failure")
async def failure():
    return HTMLResponse("<h1>❌ Pago fallido</h1><p>Intentá de nuevo.</p>")

@app.get("/pending")
async def pending():
    return HTMLResponse("<h1>⏳ Pago pendiente</h1><p>Estamos esperando confirmación.</p>")

@app.get("/health")
async def health():
    return {"status": "ok", "pedidos": len(pedidos_db)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
