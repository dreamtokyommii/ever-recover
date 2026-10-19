from core.models.file_signature import FileSignature, SignatureDatabase


def test_signature_database_import_and_listing():
    signatures = SignatureDatabase.get_all_signatures()

    assert signatures
    assert all(isinstance(signature, FileSignature) for signature in signatures)
    assert any(signature.extension == "jpg" for signature in signatures)
