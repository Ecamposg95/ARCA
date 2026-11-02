"""Lectores de archivos para importación: Toronja (HTML) y tabulares (CSV/XLSX).

Son funciones puras: bytes → filas como diccionarios. No tocan la base de
datos; la clasificación y la creación de operaciones viven en
`app/domains/imports/service.py`.
"""
