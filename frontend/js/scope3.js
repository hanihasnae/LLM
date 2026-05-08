// ═══ frontend/js/scope3.js ═══

// Mapping source_type par catégorie
const SOURCE_TYPES = {
    1: [
        { value: "steel_raw", label: "Acier brut", unit: "kg", factor: 1.85 },
        { value: "aluminum_raw", label: "Aluminium brut", unit: "kg", factor: 8.24 },
        { value: "cement_clinker", label: "Clinker ciment", unit: "kg", factor: 0.83 },
        { value: "iron_ore", label: "Minerai de fer", unit: "kg", factor: 0.02 },
        { value: "coal_coke", label: "Coke de charbon", unit: "kg", factor: 3.09 },
        { value: "limestone", label: "Calcaire", unit: "kg", factor: 0.012 },
        { value: "ammonia", label: "Ammoniac", unit: "kg", factor: 2.16 },
        { value: "bauxite", label: "Bauxite", unit: "kg", factor: 0.007 },
        { value: "scrap_metal", label: "Ferraille recyclée", unit: "kg", factor: 0.42 },
    ],
    3: [
        { value: "electricity_upstream", label: "Pertes réseau électrique", unit: "kWh", factor: 0.108 },
        { value: "fuel_upstream", label: "Extraction/raffinage fuel", unit: "litres", factor: 0.59 },
        { value: "gas_upstream", label: "Extraction/transport gaz", unit: "m3", factor: 0.41 },
    ],
    4: [
        { value: "transport_truck", label: "Camion", unit: "t.km", factor: 0.096 },
        { value: "transport_rail", label: "Train fret", unit: "t.km", factor: 0.028 },
        { value: "transport_ship", label: "Cargo maritime", unit: "t.km", factor: 0.016 },
        { value: "transport_air", label: "Fret aérien", unit: "t.km", factor: 0.602 },
    ],
    5: [
        { value: "waste_landfill", label: "Mise en décharge", unit: "kg", factor: 0.586 },
        { value: "waste_incineration", label: "Incinération", unit: "kg", factor: 0.021 },
        { value: "waste_recycling", label: "Recyclage", unit: "kg", factor: 0.010 },
    ],
    9: [
        { value: "transport_truck_out", label: "Camion (sortant)", unit: "t.km", factor: 0.096 },
        { value: "transport_ship_out", label: "Maritime (sortant)", unit: "t.km", factor: 0.016 },
        { value: "transport_rail_out", label: "Train (sortant)", unit: "t.km", factor: 0.028 },
    ],
    12: [
        { value: "end_of_life_steel", label: "Recyclage acier", unit: "kg", factor: 0.15 },
        { value: "end_of_life_aluminum", label: "Recyclage aluminium", unit: "kg", factor: 0.30 },
        { value: "end_of_life_cement", label: "Démolition béton", unit: "kg", factor: 0.01 },
        { value: "end_of_life_landfill", label: "Mise en décharge", unit: "kg", factor: 0.50 },
    ],
};

function updateFormFields() {
    const category = parseInt(document.getElementById('scope3-category').value);
    const sourceSelect = document.getElementById('scope3-source-type');
    
    // Remplir les types de source
    sourceSelect.innerHTML = '';
    const sources = SOURCE_TYPES[category] || [];
    sources.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.value;
        opt.textContent = `${s.label} (${s.factor} kg CO₂/${s.unit})`;
        sourceSelect.appendChild(opt);
    });
    
    // Afficher/masquer champs transport
    const transportFields = document.getElementById('transport-fields');
    transportFields.style.display = [4, 9].includes(category) ? 'block' : 'none';
    
    // Afficher/masquer champs fournisseur
    const supplierFields = document.getElementById('supplier-fields');
    supplierFields.style.display = category === 1 ? 'block' : 'none';
    
    // Mettre à jour l'unité
    if (sources.length > 0) {
        document.getElementById('scope3-unit').value = sources[0].unit;
    }
}

async function submitScope3Entry() {
    const category = parseInt(document.getElementById('scope3-category').value);
    
    const payload = {
        category: category,
        direction: category <= 8 ? "upstream" : "downstream",
        description: document.getElementById('scope3-description').value,
        source_type: document.getElementById('scope3-source-type').value,
        quantity: parseFloat(document.getElementById('scope3-quantity').value),
        unit: document.getElementById('scope3-unit').value,
        date: document.getElementById('scope3-date').value,
        data_quality: document.getElementById('scope3-data-quality').value,
        source_document: document.getElementById('scope3-source-doc').value || null,
    };
    
    // Champs transport
    if ([4, 9].includes(category)) {
        payload.distance_km = parseFloat(document.getElementById('scope3-distance').value) || null;
        payload.weight_tonnes = parseFloat(document.getElementById('scope3-weight').value) || null;
        payload.transport_mode = document.getElementById('scope3-transport-mode').value;
        payload.origin = document.getElementById('scope3-origin').value || null;
        payload.destination = document.getElementById('scope3-destination').value || null;
    }
    
    // Champs fournisseur
    if (category === 1) {
        payload.supplier_name = document.getElementById('scope3-supplier-name').value || null;
        payload.supplier_country = document.getElementById('scope3-supplier-country').value || null;
    }
    
    try {
        const response = await fetch('http://localhost:8000/scope3/entries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        const resultBox = document.getElementById('scope3-result');
        resultBox.style.display = 'block';
        resultBox.innerHTML = `
            <div class="result-success">
                <strong>✅ ${result.message}</strong><br>
                Catégorie : ${result.category_name}<br>
                CO₂ : ${result.co2_kg} kg (${result.co2_tonnes} tonnes)<br>
                Facteur : ${result.emission_factor} kg CO₂/unité
            </div>
        `;
        
        // Rafraîchir le dashboard
        loadScope3Data();
        
    } catch (error) {
        console.error('Erreur:', error);
        document.getElementById('scope3-result').innerHTML = 
            `<div class="result-error">❌ Erreur: ${error.message}</div>`;
    }
}

function switchDirection(direction) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-direction="${direction}"]`).classList.add('active');
    
    const select = document.getElementById('scope3-category');
    // Auto-sélectionner la première option de la direction
    if (direction === 'upstream') select.value = '1';
    else select.value = '9';
    
    updateFormFields();
}

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    updateFormFields();
});