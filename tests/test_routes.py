def test_get_messages(client, message_factory):
    # 1. Create some test data
    msg1 = message_factory(text="Hello World", channel="general")
    msg2 = message_factory(text="Alert", channel="alerts")

    # 2. Make a request to the endpoint
    response = client.get('/messages')

    # 3. Verify response
    assert response.status_code == 200
    data = response.get_json()

    print(data)
    
    assert len(data) == 2
    # Check that the data matches what we created
    assert any(m['text'] == "Hello World" for m in data)
    assert any(m['text'] == "Alert" for m in data)
